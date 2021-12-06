import asyncio
import queue
import threading
import random
from typing import Tuple

import pytest
import asyncua
from asyncio import Queue, Event
from asyncua import Node
from asyncua.ua import QualifiedName
from asyncua.ua.uaerrors import BadUserAccessDenied

from uamockapp.server import MockServer


@pytest.mark.asyncio
async def test_server_config_values(mock_server: MockServer, opcua_client: asyncua.Client):
    var1, var2, var3, _ = await _read_nodes(opcua_client)

    assert (await var1.read_value()) == 15
    assert (await var2.read_value()) == 11
    assert (await var3.read_value()) == 101


@pytest.mark.asyncio
async def test_server_config_names(mock_server: MockServer, opcua_client: asyncua.Client):
    var1, var2, var3, obj = await _read_nodes(opcua_client)

    assert (await var1.read_browse_name()) == QualifiedName("Var1", 1)
    assert (await var2.read_browse_name()) == QualifiedName("Var2", 1)
    assert (await var3.read_browse_name()) == QualifiedName("Var3", 2)
    assert (await obj.read_browse_name()) == QualifiedName("Obj", 1)


@pytest.mark.asyncio
async def test_server_config_namespaces(mock_server: MockServer, opcua_client: asyncua.Client):
    namespaces = await opcua_client.get_namespace_array()
    assert ["http://my.namespace", "http://someother.namespace"] == namespaces[2:]


async def _read_nodes(opcua_client: asyncua.Client) -> Tuple[Node, Node, Node, Node]:
    var1 = opcua_client.get_node("ns=1;i=10000")
    var2 = opcua_client.get_node("ns=1;i=10001")
    obj = opcua_client.get_node("ns=1;i=10002")
    var3 = opcua_client.get_node("ns=2;i=20001")

    return var1, var2, var3, obj


@pytest.mark.asyncio
async def test_server_read_node_by_name(mock_server: MockServer):
    val = await mock_server.read("Obj/2:Var3")
    assert val == 101


@pytest.mark.asyncio
async def test_server_read_nonexistent_node_by_name(mock_server: MockServer):
    with pytest.raises(ValueError):
        await mock_server.read("ObjNonexistent")


@pytest.mark.asyncio
async def test_server_write_node_by_name(mock_server: MockServer, opcua_client: asyncua.Client):
    await mock_server.write("Var2", 10000)
    value = await opcua_client.get_node("ns=1;i=10001").read_value()

    assert 10000 == value


@pytest.mark.asyncio
async def test_server_write_nonexistent_node_by_name(mock_server: MockServer, opcua_client: asyncua.Client):
    with pytest.raises(ValueError):
        await mock_server.write("VarNonexistent", 10000)


@pytest.mark.asyncio
async def test_server_external_write_write_enabled(mock_server: MockServer, opcua_client: asyncua.Client):
    await opcua_client.get_node("ns=1;i=10001").write_value(0)


@pytest.mark.asyncio
async def test_server_external_write_write_disabled(mock_server: MockServer, opcua_client: asyncua.Client):
    with pytest.raises(BadUserAccessDenied):
        await opcua_client.get_node("ns=1;i=10002").write_value(0)


@pytest.mark.asyncio
@pytest.mark.parametrize('n', range(5))
async def test_server_wait_for_predicate_not_fulfilled(mock_server: MockServer, opcua_client: asyncua.Client, n):
    await mock_server.write("Var2", 0)

    wait_task = asyncio.create_task(
        mock_server.wait_for("Var2", 100, 0.2)
    )

    # Write some other value and check if the wait is not triggered
    await mock_server.write("Var2", 10)
    with pytest.raises(asyncio.TimeoutError):
        await wait_task


@pytest.mark.asyncio
@pytest.mark.parametrize('n', range(5))
async def test_server_wait_for_predicate_fulfilled(mock_server: MockServer, opcua_client: asyncua.Client, n):
    await mock_server.write("Var2", 0)

    wait_task = asyncio.create_task(
        mock_server.wait_for("Var2", 100, 3)
    )

    # Write the expected value and check for it
    await mock_server.write("Var2", 100)
    await wait_task


@pytest.mark.asyncio
async def test_server_on_change_sync_cbk(mock_server: MockServer, opcua_client: asyncua.Client):
    await mock_server.write("Var2", 0)

    evt = threading.Event()
    await mock_server.on_change(
        "Var2", lambda _: evt.set()
    )

    assert not evt.is_set()

    await opcua_client.get_node("ns=1;i=10001").write_value(100)
    evt.wait(1)
    assert evt.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize('n', range(5))
async def test_server_on_change_async_cbk(mock_server: MockServer, opcua_client: asyncua.Client, n):
    await mock_server.write("Var2", 0)

    event = Event()

    async def cbk(val):
        if val == 100:
            event.set()

    await mock_server.on_change(
        "Var2", cbk
    )

    await opcua_client.get_node("ns=1;i=10001").write_value(100)
    await asyncio.wait_for(event.wait(), 1)

    assert event.is_set()


@pytest.mark.asyncio
async def test_server_on_change_write_server_from_async_cbk(mock_server: MockServer, opcua_client: asyncua.Client):
    expected_value = random.randint(1, 500)
    await mock_server.write("Var2", 0)

    async def cbk(val):
        if val == 100:
            await mock_server.write("Var2", expected_value)

    await mock_server.on_change(
        "Var2", cbk
    )

    await opcua_client.get_node("ns=1;i=10001").write_value(100)
    await mock_server.wait_for("Var2", expected_value, 1)

    assert (await mock_server.read("Var2")) == expected_value
