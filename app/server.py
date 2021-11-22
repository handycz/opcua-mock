import datetime
import itertools
import logging

from pydantic.dataclasses import dataclass
from typing import Any, Union, Coroutine, Callable, Dict, List, Iterable, Tuple, Set, Optional


import asyncio
import yaml
from asyncio import AbstractEventLoop, Condition
from asyncua import Server, Node, ua
from asyncua.common.subscription import Subscription
from asyncua.server.history import HistoryStorageInterface, UaNodeAlreadyHistorizedError
from asyncua.tools import SubHandler
from asyncua.ua import NodeId, QualifiedName, DataChangeNotification, DataValue
from asyncua.ua.uaerrors import BadNoMatch, BadNodeIdUnknown
from yaml import Loader

from app.utils import lazyeval


@dataclass
class FunctionDescription:
    name: str
    args: Optional[List[str]]


@dataclass
class HistorySample:
    value: Any
    timestamp: datetime.datetime


@dataclass
class OnChangeDescription:
    var_name: str
    history: List[HistorySample]


@dataclass
class DataImageItemValue:
    value: Any
    history: List[HistorySample]


class MockFunction:
    _logger: logging.Logger
    _name: str
    _callback: Callable[..., Union[None, Coroutine[Any, Any, None]]]
    _arg_types: Iterable[type]
    _loop: AbstractEventLoop

    @property
    def args(self) -> Optional[Iterable[type]]:
        if self._arg_types is None:
            return None

        return list(self._arg_types)

    def __init__(
            self, name: str, callback: Callable[..., Union[None, Coroutine[Any, Any, None]]], arg_types: Iterable[type]
    ):
        self._logger = logging.getLogger(__name__)
        self._name = name
        self._callback = callback
        self._arg_types = arg_types
        self._loop = asyncio.get_event_loop()

    def call(self, arg_list: Tuple[Any]):
        self._logger.info("Calling method %s with args %s", self._name, lazyeval(
                lambda: ", ".join((str(a) for a in arg_list))
            )
        )

        if self._loop is None:
            raise RuntimeError("Loop was not defined, init was probably not called")

        num = 0
        if self._arg_types is None:
            arg_types = [None] * len(arg_list)
        else:
            arg_types = self._arg_types

        for arg_type, arg in itertools.zip_longest(arg_types, arg_list):
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


# todo: proper subscription management... count active subscriptions and un-subscribe or re-subscribe when necessary
class NotificationHandler(SubHandler):
    _logger: logging.Logger
    _notify: Dict[NodeId, Condition]
    _callbacks: Dict[NodeId, List[MockFunction]]
    _nodes_watched_for_change: Set[str]

    @property
    def nodes_watched_for_change(self) -> Iterable[str]:
        return set(self._nodes_watched_for_change)

    def __init__(self):
        self._logger = logging.getLogger(__name__)
        self._notify = dict()
        self._callbacks = dict()
        self._nodes_watched_for_change = set()

    async def register_notify(self, node_id: NodeId) -> Condition:
        # TODO: clean this up after it's not needed... maybe by a weak ref dict?
        if node_id in self._notify:
            return self._notify[node_id]

        self._notify[node_id] = Condition()
        return self._notify[node_id]

    def register_callback(self, node_name: str, node_id: NodeId, callback: MockFunction):
        if node_id not in self._callbacks:
            self._callbacks[node_id] = list()

        if callback not in self._callbacks[node_id]:
            self._callbacks[node_id].append(callback)
            self._nodes_watched_for_change.add(node_name)
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


class SimpleDataHistoryDict(HistoryStorageInterface):
    """
    Very minimal history backend storing data in memory using a Python dictionary
    """

    def __init__(self, max_history_data_response_size=10000):
        self.max_history_data_response_size = max_history_data_response_size
        self._datachanges = {}
        self._datachanges_period = {}
        self._events = {}
        self._events_periods = {}

    async def init(self):
        pass

    async def new_historized_node(self, node_id, period, count=0):
        if node_id in self._datachanges:
            raise UaNodeAlreadyHistorizedError(node_id)
        self._datachanges[node_id] = []
        self._datachanges_period[node_id] = period, count

    async def save_node_value(self, node_id, datavalue):
        data = self._datachanges[node_id]
        period, count = self._datachanges_period[node_id]
        data.append(datavalue)
        now = datetime.datetime.utcnow()
        if period:
            while len(data) and now - data[0].SourceTimestamp > period:
                data.pop(0)
        if count and len(data) > count:
            data.pop(0)

    async def read_node_history(self, node_id, start, end, nb_values):
        cont = None
        if node_id not in self._datachanges:
            # logger.warning("Error attempt to read history for a node which is not historized")
            return [], cont
        else:
            if start is None:
                start = ua.get_win_epoch()
            if end is None:
                end = ua.get_win_epoch()
            if start == ua.get_win_epoch():
                print(self._datachanges[node_id])

                results = [
                    dv
                    for dv in reversed(self._datachanges[node_id])
                ]
            elif end == ua.get_win_epoch():
                results = [dv for dv in self._datachanges[node_id]]
            elif start > end:
                results = [
                    dv
                    for dv in reversed(self._datachanges[node_id])
                ]

            else:
                results = [
                    dv for dv in self._datachanges[node_id]
                ]

            if nb_values and len(results) > nb_values:
                results = results[:nb_values]

            if len(results) > self.max_history_data_response_size:
                cont = results[self.max_history_data_response_size + 1].SourceTimestamp
                results = results[:self.max_history_data_response_size]
            return results, cont

    async def new_historized_event(self, source_id, evtypes, period, count=0):
        raise NotImplementedError()

    async def save_event(self, event):
        raise NotImplementedError()

    async def read_event_history(self, source_id, start, end, nb_values, evfilter):
        raise NotImplementedError()

    async def stop(self):
        pass


class MockServer:
    _logger: logging.Logger
    _server: Server
    _config_path: str
    _functions: Dict[str, MockFunction]
    _node_name_list: List[str]
    _notification_handler: NotificationHandler
    _subscription: Subscription

    def __init__(self, config_path: str):
        self._logger = logging.getLogger(__name__)
        self._server = Server()
        self._config_path = config_path
        self._functions = dict()
        self._notification_handler = NotificationHandler()
        self._node_name_list = list()

    async def init(self):
        self._server.iserver.history_manager.set_storage(SimpleDataHistoryDict())
        await self._server.init()
        config = self._read_config()
        self._subscription = await self._server.create_subscription(10, self._notification_handler)

        self._server.set_endpoint(config["server"]["endpoint"])
        self._server.set_server_name(config["server"]["name"])
        await self._create_namespaces(config["server"]["namespaces"])
        await self._create_node_level(config["nodes"], self._server.get_objects_node(), "")

    async def __aenter__(self):
        await self._server.start()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._server.stop()

    async def start(self):
        await self._server.start()

    async def stop(self):
        await self._server.stop()

    async def _create_namespaces(self, namespaces: List[str]):
        for ns in namespaces:
            self._logger.debug("Adding namespace %s", ns)
            await self._server.register_namespace(ns)

    async def _create_node_level(self, nodes: Dict[str, Any], parent: Node, parent_name: str):
        for node_description in nodes:
            node_description: Dict[str, Any]

            node_type = node_description["type"].lower()
            nodeid = NodeId.from_string(node_description["nodeid"])
            browsename = QualifiedName(node_description["name"], nodeid.NamespaceIndex)
            value: Union[Any, Dict[str, Any]] = node_description["value"]
            writable: bool = node_description["writable"] if "writable" in node_description else False
            full_name = browsename.to_string() if parent_name == "" else parent_name + "/" + browsename.to_string()
            hist_count: int = node_description["samples"] if "samples" in node_description else 10

            if node_type == "object":
                obj = await parent.add_object(
                    nodeid,
                    browsename
                )
                await self._create_node_level(
                    value, obj, full_name
                )

            elif node_type == "variable":
                var = await parent.add_variable(
                    nodeid,
                    browsename,
                    value
                )

                if writable:
                    await var.set_writable(True)
                    self._logger.info("Node %s is writable", full_name)

                await self._server.historize_node_data_change(var, period=None, count=hist_count)
                self._logger.info("Node %s is historized (count: %s)", full_name, hist_count)

                self._node_name_list.append(full_name)

            else:
                raise ValueError(f"Unknown node type {node_type}")

    def _read_config(self) -> Dict[str, Any]:
        with open(self._config_path) as f:
            return yaml.load(f, Loader)

    async def read(self, name: str = None, nodeid: str = None) -> Any:
        """
        Reads a value of a variable given by its name or nodeid. The name of the
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

    async def read_history(self, name: str = None, nodeid: str = None, num_values: int = 0) -> List[HistorySample]:
        """
        Reads a value of a variable given by its name or nodeid. The name of the
        variable is a string of node names in the browse path separated by slashes relative
        to the objects node. If a parent has multiple nodes of the same name in
        different namespaces, the namespace can be specified as "<namespace idx>:<node name>".
        Example of the browse path is "MainFolder/ParentObject/3:MyVariable".
        :param name: path to the variable
        :param nodeid: nodeid of the variable
        :param num_values: number of history values to read (0 for all values)
        """
        try:
            if nodeid is not None:
                raw_values: List[DataValue] = await self._server.get_node(nodeid).read_raw_history(numvalues=num_values)
            elif name is not None:
                node = await self._browse_path(name)
                # fixme: await node.read_value() blocks when used in the MockServer.wait_for().. why?
                raw_values: List[DataValue] = await node.read_raw_history(numvalues=num_values)
            else:
                raise ValueError("Either name or nodeid has to be specified")
        except (BadNoMatch, BadNodeIdUnknown) as e:
            raise ValueError("Unknown variable identifier", e)

        values = [
            HistorySample(
                value.Value.Value, value.SourceTimestamp.replace(tzinfo=datetime.timezone.utc)
                if value.SourceTimestamp else None
            ) for value in raw_values
        ]

        self._logger.info("Read history of %s, len = %s", name, len(values))
        return values

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
            self, var_name: str, callback: Callable[[Any], Union[None, Coroutine[Any, Any, None]]],
            arg_type: type = None
    ) -> None:
        node_to_watch = await self._browse_path(var_name)
        self._notification_handler.register_callback(
            var_name,
            node_to_watch.nodeid,
            MockFunction(
                var_name,
                callback,
                [arg_type]
            )
        )
        # todo: save the subscription handle to allow de-registration
        await self._subscription.subscribe_data_change(node_to_watch)

    async def on_call(
            self, function_name: str, callback: Callable[..., Union[None, Coroutine[Any, Any, None]]],
            arg_types: Iterable[type] = None
    ) -> None:
        if function_name in self._functions:
            raise ValueError("Callable already exists")

        self._functions[function_name] = MockFunction(
            function_name,
            callback,
            arg_types
        )

    async def call(self, name: str, *args: Any):
        if name not in self._functions:
            raise ValueError("Unknown callable")

        self._functions[name].call(args)

    async def get_data_image(self) -> Dict[str, DataImageItemValue]:
        data_img = dict()

        for node_name in self._node_name_list:
            hist = await self.read_history(node_name)
            data_img[node_name] = DataImageItemValue(
                value=hist[0].value,
                history=hist
            )

        return data_img

    async def get_function_list(self) -> List[FunctionDescription]:
        fcn_list = list()

        for name, func in self._functions.items():
            fcn_list.append(
                FunctionDescription(
                    name,
                    [arg.__name__ for arg in func.args] if func.args is not None else None
                )
            )

        return fcn_list

    async def get_onchange_list(self) -> List[OnChangeDescription]:
        onchange_list = list()

        for node_name in self._notification_handler.nodes_watched_for_change:
            onchange_list.append(
                OnChangeDescription(
                    node_name,
                    await self.read_history(name=node_name)
                )
            )

        return onchange_list
