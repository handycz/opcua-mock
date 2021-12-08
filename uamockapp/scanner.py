import logging
import sys
from typing import Any, Dict, List, Union
from urllib.parse import urlparse

import yaml
from asyncua import Client, Node, ua
from asyncua.ua import NodeClass, AccessLevel

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stdout))


async def generate_server_config(url: str, config_path: str) -> None:
    conf = await scan_server(url)
    with open(config_path, "w") as f:
        yaml.dump(conf, f, yaml.Dumper)


async def scan_server(url: str) -> Dict[str, Any]:
    async with Client(url) as connection:
        server_config = await _read_server_config(connection)
        server_nodes = await _read_server_nodes(connection)

    return {
        "server": server_config,
        "nodes": server_nodes
    }


async def _read_server_config(connection: Client) -> Dict[str, Any]:
    url = connection.server_url
    url = urlparse(url.geturl().replace(url.netloc, "0.0.0.0")).geturl()

    return {
        "endpoint": url,
        "name": await connection.get_node(ua.ObjectIds.Server_ServerStatus_BuildInfo_ProductName).get_value(),
        "namespaces": [
            ns for ns in (await connection.get_namespace_array())[2:]
        ]
    }


async def _read_server_nodes(connection: Client) -> List[Dict[str, Any]]:
    return await _explore_nodes(connection.get_objects_node())


async def _explore_nodes(parent: Node) -> List[Dict[str, Any]]:
    logger.info("Exploring %s", parent)

    scans = [_scan_child_node(node) for node in await parent.get_children()]
    nodes = list(filter(
        lambda val: val is not None,
        await asyncio.gather(*scans)
    ))
    return nodes


async def _scan_child_node(child: Node):
        name = (await child.read_browse_name()).Name
        logger.debug("Scanning %s (%s)", name, child)

        if name == "Server":
            logger.info("Skipping Server node")
            return

        if name == "DeviceSet":
            logger.info("Skipping DeviceSet node")
            return

        cls = await child.read_node_class()
        nodeid = child.nodeid.to_string()

        if cls == NodeClass.Object:
            value = await _explore_nodes(child)
            writable = False
        elif cls == NodeClass.Variable:
            value = await child.read_value()
            writable = await _get_node_writable(child)

        else:
            logger.warning("Ignoring node %s of type %s", name, cls)
            return

        return {
            "nodeid": nodeid,
            "name": name,
            "type": cls.name.lower(),
            "writable": writable,
            "samples": 10,
            "value": value
        }


async def _get_node_writable(node: Node) -> bool:
    access_level = await node.get_access_level()
    user_access_level = await node.get_user_access_level()

    return access_level == AccessLevel.CurrentWrite and user_access_level == AccessLevel.CurrentWrite
