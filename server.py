from typing import Any, Union, Coroutine, Callable, Dict, List

import yaml
from asyncua import Server, Node
from yaml import Loader


class MockServer:
    _server: Server
    _config_path: str

    def __init__(self, config_path: str):
        self._server = Server()
        self._config_path = config_path

    async def init(self):
        await self._server.init()
        config = self._read_config()

        self._server.set_endpoint(config["server"]["endpoint"])
        self._server.set_server_name(config["server"]["name"])
        await self._create_namespaces(config["namespaces"])
        await self._create_node_level(config["nodes"], self._server.get_objects_node())

    async def _create_namespaces(self, namespaces: List[str]):
        for ns in namespaces:
            return await self._server.register_namespace(ns)

    async def _create_node_level(self, nodes: Dict[str, Any], parent: Node):
        for node_description in nodes:
            node_description: Dict[str, Any]

            if node_description["type"] == "object":
                await self._create_object(
                    node_description["nodeid"],
                    node_description["name"],
                    node_description["value"],
                    parent
                )
            else:
                await parent.add_variable(
                    node_description["nodeid"],
                    node_description["name"],
                    node_description["value"],
                )

    def _read_config(self) -> Dict[str, Any]:
        with open(self._config_path) as f:
            return yaml.load(f, Loader)

    async def _create_object(self, nodeid: str, name: str, nodes: Dict[str, Any], parent: Node):
        obj = await parent.add_object(
            nodeid,
            name
        )

        await self._create_node_level(nodes, obj)

    async def read(self, name: str = None, nodeid: str = None) -> Any:
        if nodeid is not None:
            return await self._server.get_node(nodeid).read_value()
        elif name is not None:
            node = await self._server.get_objects_node().get_child(self._get_node_path(name))
            return await node.read_value()
        else:
            raise ValueError("Either name or nodeid has to be specified")

    async def write(self, value: Any, name: str = None, nodeid: str = None) -> None:
        if nodeid is not None:
            return await self._server.get_node(nodeid).read_value()
        elif name is not None:
            node = await self._server.get_objects_node().get_child(self._get_node_path(name))
            await node.write_value(value)
        else:
            raise ValueError("Either name or nodeid has to be specified")

    def _get_node_path(self, name: str) -> List[str]:
        return name.split(".")

    async def wait_for(self, name: str, value: Any) -> None:
        pass

    async def on_change(self, name: str, callback: Union[Coroutine[Any, Any, Any], Callable[[Any], None]]) -> None:
        pass
