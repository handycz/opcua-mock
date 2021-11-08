import itertools
import logging
from typing import Any, Union, Coroutine, Callable, Dict, List

import asyncio
import yaml
from asyncio import Event, AbstractEventLoop, Condition
from asyncua import Server, Node
from asyncua.common.subscription import Subscription
from asyncua.tools import SubHandler
from asyncua.ua import NodeId, QualifiedName, DataChangeNotification
from asyncua.ua.uaerrors import BadNoMatch, BadNodeIdUnknown
from yaml import Loader

from app.utils import lazyeval


class MockFunction:
    _logger: logging.Logger
    _name: str
    _callback: Callable[..., Union[None, Coroutine[Any, Any, None]]]
    _arg_types: List[type]
    _loop: AbstractEventLoop

    def __init__(
            self, name: str, callback: Callable[..., Union[None, Coroutine[Any, Any, None]]], arg_types: List[type]
    ):
        self._logger = logging.getLogger(__name__)
        self._name = name
        self._callback = callback
        self._arg_types = arg_types
        self._loop = asyncio.get_event_loop()

    def call(self, arg_list: List[Any]):
        self._logger.info("Calling method %s with args %s", self._name, lazyeval(
                lambda: ", ".join((str(a) for a in arg_list))
            )
        )

        if self._loop is None:
            raise RuntimeError("Loop was not defined, init was probably not called")

        num = 0
        for arg_type, arg in itertools.zip_longest(self._arg_types, arg_list):
            num += 1

            if arg_type is None:
                self._logger.info("Skipping argument type check for argument number %s", num)
                continue

            if not isinstance(arg, arg_type):
                raise TypeError(f"Wrong type of argument number {num}, expected {arg_type} got {type(arg)}")

        try:
            if asyncio.iscoroutinefunction(self._callback):
                self._logger.debug("Calling coroutine")
                asyncio.run_coroutine_threadsafe(self._callback(*arg_list), self._loop)
            else:
                self._callback(*arg_list)
        except Exception as e:
            raise TypeError("An error occurred during the function call", e)


class NotificationHandler(SubHandler):
    _logger: logging.Logger
    _notify: Dict[NodeId, Condition]
    _callbacks: Dict[NodeId, List[MockFunction]]

    def __init__(self):
        self._logger = logging.getLogger(__name__)
        self._notify = dict()
        self._callbacks = dict()

    async def register_notify(self, node_id: NodeId) -> Condition:
        # TODO: clean this up after it's not needed... maybe by a weak ref dict?
        if node_id in self._notify:
            return self._notify[node_id]

        self._notify[node_id] = Condition()
        return self._notify[node_id]

    def register_callback(self, node_id: NodeId, callback: MockFunction):
        if node_id not in self._callbacks:
            self._callbacks[node_id] = list()

        if callback not in self._callbacks[node_id]:
            self._callbacks[node_id].append(callback)
        else:
            self._logger.warning("Mock function already registered, ignoring")

    async def datachange_notification(self, node: Node, val: Any, data: DataChangeNotification):
        self._logger.info("Datachange notification of %s to %s", node, val)

        if node.nodeid in self._notify:
            cond = self._notify[node.nodeid]
            async with cond:
                cond.notify_all()

        if node.nodeid in self._callbacks:
            for func in self._callbacks[node.nodeid]:
                func.call([val])


class MockServer:
    _logger: logging.Logger
    _server: Server
    _config_path: str
    _functions: Dict[str, MockFunction]
    _notification_handler: NotificationHandler
    _subscription: Subscription

    def __init__(self, config_path: str):
        self._logger = logging.getLogger(__name__)
        self._server = Server()
        self._config_path = config_path
        self._functions = dict()
        self._notification_handler = NotificationHandler()

    async def init(self):
        await self._server.init()
        config = self._read_config()
        self._subscription = await self._server.create_subscription(10, self._notification_handler)

        self._server.set_endpoint(config["server"]["endpoint"])
        self._server.set_server_name(config["server"]["name"])
        await self._create_namespaces(config["server"]["namespaces"])
        await self._create_node_level(config["nodes"], self._server.get_objects_node())

    async def __aenter__(self):
        await self._server.start()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._server.stop()

    async def _create_namespaces(self, namespaces: List[str]):
        for ns in namespaces:
            self._logger.debug("Adding namespace %s", ns)
            await self._server.register_namespace(ns)

    async def _create_node_level(self, nodes: Dict[str, Any], parent: Node):
        for node_description in nodes:
            node_description: Dict[str, Any]

            node_type = node_description["type"].lower()

            nodeid = NodeId.from_string(node_description["nodeid"])
            browsename = QualifiedName(node_description["name"], nodeid.NamespaceIndex)

            if node_type == "object":
                obj = await parent.add_object(
                    nodeid,
                    browsename
                )
                await self._create_node_level(node_description["value"], obj)

            elif node_type == "variable":
                var = await parent.add_variable(
                    nodeid,
                    browsename,
                    node_description["value"]
                )

                if "writable" in node_description and node_description["writable"]:
                    await var.set_writable(True)

            else:
                raise ValueError(f"Unknown node type {node_type}")

    def _read_config(self) -> Dict[str, Any]:
        with open(self._config_path) as f:
            return yaml.load(f, Loader)

    async def read(self, name: str = None, nodeid: str = None) -> Any:
        """
        Writes a value of a variable given by its name or nodeid. The name of the
        variable is a string of node names in the browse path separated by slashes relative
        to the objects node. If a parent has multiple nodes of the same name in
        different namespaces, the namespace can be specified as "<namespace idx>:<node name>".
        Example of the browse path is "MainFolder/ParentObject/3:MyVariable".
        :param name: path to the variable
        :param nodeid: nodeid of the variable
        """
        try:
            if nodeid is not None:
                value = await self._server.get_node(nodeid).read_value()
            elif name is not None:
                node = await self._browse_path(name)
                # fixme: await node.read_value() blocks when used in the MockServer.wait_for().. why?
                value = await asyncio.create_task(node.read_value())
            else:
                raise ValueError("Either name or nodeid has to be specified")
        except (BadNoMatch, BadNodeIdUnknown) as e:
            raise ValueError("Unknown variable identifier", e)

        self._logger.info("Read value of %s = %s", name, value)
        return value

    async def write(self, value: Any, name: str = None, nodeid: str = None) -> None:
        """
        Writes a value to a variable given by its name or nodeid. The name of the
        variable is a string of node names in the browse path separated by slashes relative
        to the objects node. If a parent has multiple nodes of the same name in
        different namespaces, the namespace can be specified as "<namespace idx>:<node name>".
        Example of the browse path is "MainFolder/ParentObject/3:MyVariable".
        :param value: value to write
        :param name: path to the variable
        :param nodeid: nodeid of the variable
        """

        try:
            if nodeid is not None:
                return await self._server.get_node(nodeid).read_value()
            elif name is not None:
                node = await self._browse_path(name)
                await node.write_value(value)
            else:
                raise ValueError("Either name or nodeid has to be specified")
        except (BadNoMatch, BadNodeIdUnknown) as e:
            raise ValueError("Unknown variable identifier", e)

        self._logger.info("Written value of %s = %s", name, value)

    async def _browse_path(self, path: str) -> Node:
        node_names = path.split("/")
        parent = self._server.get_objects_node()

        for node_name in node_names:
            if ":" in node_name:
                parent = await parent.get_child(node_name)
            else:
                parent = await self._find_matching_child(parent, node_name)

        return parent

    @staticmethod
    async def _find_matching_child(parent: Node, node_name: str) -> Node:
        matches = list()
        children = await parent.get_children()

        for child in children:
            if (await child.read_browse_name()).Name == node_name:
                matches.append(child)

        if len(matches) == 0:
            raise ValueError(f"Node '{node_name}' undefined")
        if len(matches) == 1:
            parent = matches.pop()
        else:
            raise ValueError(f"Node name '{node_name} ambiguous")

        return parent

    async def wait_for(self, name: str, value: Any, timeout: float = None) -> None:
        node_to_watch = await self._browse_path(name)
        cond = await self._notification_handler.register_notify(node_to_watch.nodeid)
        monitor_handle = await self._subscription.subscribe_data_change(node_to_watch)

        await asyncio.wait_for(
            self._wait_for_value_read(name, value, cond),
            timeout
        )

        await self._subscription.unsubscribe(monitor_handle)

    async def _wait_for_value_read(self, name: str, value: Any, change_notification: Condition):
        read = None
        async with change_notification:
            while read != value:
                read = await self.read(name)

    async def on_change(
            self, name: str, callback: Callable[[Any], Union[None, Coroutine[Any, Any, None]]],
            arg_type: type = None
    ) -> None:
        node_to_watch = await self._browse_path(name)
        self._notification_handler.register_callback(
            node_to_watch.nodeid,
            MockFunction(
                name,
                callback,
                [arg_type]
            )
        )
        # todo: save the subscription handle to allow de-registration
        await self._subscription.subscribe_data_change(node_to_watch)

    async def on_call(
            self, name: str, callback: Callable[..., Union[None, Coroutine[Any, Any, None]]],
            arg_types: List[type] = None
    ) -> None:
        if name in self._functions:
            raise ValueError("Callable already exists")

        self._functions[name] = MockFunction(
            name,
            callback,
            arg_types
        )

    async def call(self, name: str, args: List[Any]):
        if name not in self._functions:
            raise ValueError("Unknown callable")

        self._functions[name].call(args)
