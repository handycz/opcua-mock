import itertools
import logging
from typing import Any, Union, Coroutine, Callable, Dict, List

import asyncio
import yaml
from asyncio import Event, AbstractEventLoop, Condition
from asyncua import Server, Node
from asyncua.tools import SubHandler
from asyncua.ua import NodeId, QualifiedName
from asyncua.ua.uaerrors import BadNoMatch
from yaml import Loader


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
        self._logger.info("Calling method % with args %", self._name, lambda: ", ".join(arg_list))

        if self._loop is None:
            raise RuntimeError("Loop was not defined, init was probably not called")

        num = 0
        for arg_type, arg in itertools.zip_longest(self._arg_types, arg_list):
            num += 1

            if arg_type is None:
                self._logger.info("Skipping argument type check for argument number %", num)

            if not isinstance(arg, arg_type):
                raise TypeError(f"Wrong type of argument number {num}, expected {arg_type} got {type(arg)}")

        try:
            if asyncio.iscoroutinefunction(self._callback):
                self._loop.call_soon_threadsafe(self._callback, *arg_list)
            else:
                self._callback(*arg_list)
        except Exception as e:
            raise TypeError("An error occured during the function call", e)


class NotificationHandler(SubHandler):
    _logger: logging.Logger
    _notify: Dict[str, Condition]
    _callbacks: Dict[str, List[MockFunction]]

    def __init__(self):
        self._logger = logging.getLogger(__name__)
        self._notify = dict()
        self._callbacks = dict()

    async def register_notify(self, name: str) -> Condition:
        # TODO: clean this up after it's not needed... maybe by a weak ref dict?
        if name in self._notify:
            return self._notify[name]

        self._notify[name] = Condition()
        return self._notify[name]

    def register_callback(self, name: str, callback: MockFunction):
        if name not in self._callbacks:
            self._callbacks[name] = list()

        if callback not in self._callbacks[name]:
            self._callbacks[name].append(callback)
        else:
            self._logger.warning("Mock function already registered, ignoring")

    async def datachange_notification(self, node, val, data):
        node_name = ...

        if node_name in self._notify:
            cond = self._notify[node_name]
            async with cond:
                cond.notify_all()

        if node_name in self._callbacks:
            for func in self._callbacks[node_name]:
                func.call([val])


class MockServer:
    _logger: logging.Logger
    _server: Server
    _config_path: str
    _functions: Dict[str, MockFunction]
    _notification_handler: NotificationHandler

    def __init__(self, config_path: str):
        self._logger = logging.getLogger(__name__)
        self._server = Server()
        self._config_path = config_path
        self._functions = dict()
        self._notification_handler = NotificationHandler()

    async def init(self):
        await self._server.init()
        config = self._read_config()
        await self._server.create_subscription(10, self._notification_handler)

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
                await parent.add_variable(
                    nodeid,
                    browsename,
                    node_description["value"]
                )

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
                node = await self._server.get_objects_node().get_child(self._get_node_path(name))
                value = await node.read_value()
            else:
                raise ValueError("Either name or nodeid has to be specified")
        except BadNoMatch as e:
            raise ValueError("Unknown variable name")

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
                node = await self._server.get_objects_node().get_child(self._get_node_path(name))
                await node.write_value(value)
            else:
                raise ValueError("Either name or nodeid has to be specified")
        except BadNoMatch as e:
            raise ValueError("Unknown variable name")

        self._logger.info("Written value of %s = %s", name, value)

    def _get_node_path(self, name: str) -> List[str]:
        return name.split("/")

    async def wait_for(self, name: str, value: Any) -> None:
        cond = await self._notification_handler.register_notify(name)
        loop = asyncio.get_running_loop()
        await cond.wait_for(lambda: loop.call_soon_threadsafe(self.read, name) == value)

    async def on_change(
            self, name: str, callback: Callable[..., Union[None, Coroutine[Any, Any, None]]],
            arg_type: type = None
    ) -> None:
        self._notification_handler.register_callback(
            name,
            MockFunction(
                name,
                callback,
                [arg_type]
            )
        )

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
