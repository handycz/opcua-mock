import asyncio
import logging
from typing import Tuple

import pytest
import asyncua
from asyncua import Node
from asyncua.ua import QualifiedName

from app.server import MockServer


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module", autouse=True)
async def mock_server():
    server = MockServer(
        "test_server_config.yaml"
    )

    await server.init()
    async with server:
        yield server


@pytest.fixture(scope="module")
async def opcua_client():
    client = asyncua.Client("opc.tcp://localhost:4840")
    async with client:
        yield client


@pytest.mark.asyncio
async def test_server_config_values(opcua_client: asyncua.Client):
    var1, var2, var3, _ = await _read_nodes(opcua_client)

    assert (await var1.read_value()) == 15
    assert (await var2.read_value()) == 11
    assert (await var3.read_value()) == 101


@pytest.mark.asyncio
async def test_server_config_names(opcua_client: asyncua.Client):
    var1, var2, var3, obj = await _read_nodes(opcua_client)

    assert (await var1.read_browse_name()) == QualifiedName("Var1", 1)
    assert (await var2.read_browse_name()) == QualifiedName("Var2", 1)
    assert (await var3.read_browse_name()) == QualifiedName("Var3", 2)
    assert (await obj.read_browse_name()) == QualifiedName("Obj", 1)


@pytest.mark.asyncio
async def test_server_config_namespaces(opcua_client: asyncua.Client):
    namespaces = await opcua_client.get_namespace_array()
    assert ["http://my.namespace", "http://someother.namespace"] == namespaces[2:]


async def _read_nodes(opcua_client: asyncua.Client) -> Tuple[Node, Node, Node, Node]:
    var1 = opcua_client.get_node("ns=1;i=10000")
    var2 = opcua_client.get_node("ns=1;i=10001")
    obj = opcua_client.get_node("ns=1;i=10002")
    var3 = opcua_client.get_node("ns=2;i=20001")

    return var1, var2, var3, obj
