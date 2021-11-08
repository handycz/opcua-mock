import asyncio
import logging
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


@pytest.mark.asyncio
async def test_server_read_node_by_name(mock_server: MockServer):
    val = await mock_server.read(name="Obj/2:Var3")
    assert val == 101


@pytest.mark.asyncio
async def test_server_read_node_by_id(mock_server: MockServer):
    val = await mock_server.read(nodeid="ns=1;i=10001")
    assert val == 11


@pytest.mark.asyncio
async def test_server_read_nonexistent_node_by_name(mock_server: MockServer):
    with pytest.raises(ValueError):
        await mock_server.read(name="ObjNonexistent")


@pytest.mark.asyncio
async def test_server_read_nonexistent_node_by_id(mock_server: MockServer):
    with pytest.raises(ValueError):
        await mock_server.read(nodeid="ns=1;i=10")


@pytest.mark.asyncio
async def test_server_write_node_by_name(mock_server: MockServer, opcua_client: asyncua.Client):
    await mock_server.write(10000, name="Var2")
    value = await opcua_client.get_node("ns=1;i=10001").read_value()

    assert 10000 == value


@pytest.mark.asyncio
async def test_server_write_node_by_id(mock_server: MockServer, opcua_client: asyncua.Client):
    await mock_server.write(20000, nodeid="ns=1;i=10001")
    value = await opcua_client.get_node("ns=1;i=10001").read_value()

    assert 10000 == value


@pytest.mark.asyncio
async def test_server_write_nonexistent_node_by_name(mock_server: MockServer, opcua_client: asyncua.Client):
    with pytest.raises(ValueError):
        await mock_server.write(10000, name="VarNonexistent")


@pytest.mark.asyncio
async def test_server_write_nonexistent_node_by_id(mock_server: MockServer, opcua_client: asyncua.Client):
    with pytest.raises(ValueError):
        await mock_server.write(20000, nodeid="ns=1;i=100000")


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
    await mock_server.write(0, "Var2")

    wait_task = asyncio.create_task(
        mock_server.wait_for("Var2", 100, 0.2)
    )

    # Write some other value and check if the wait is not triggered
    await mock_server.write(10, "Var2")
    with pytest.raises(asyncio.TimeoutError):
        await wait_task


@pytest.mark.asyncio
@pytest.mark.parametrize('n', range(5))
async def test_server_wait_for_predicate_fulfilled(mock_server: MockServer, opcua_client: asyncua.Client, n):
    await mock_server.write(0, "Var2")

    wait_task = asyncio.create_task(
        mock_server.wait_for("Var2", 100, 3)
    )

    # Write the expected value and check for it
    await mock_server.write(100, "Var2")
    await wait_task


@pytest.mark.asyncio
async def test_server_on_change_sync_cbk(mock_server: MockServer, opcua_client: asyncua.Client):
    await mock_server.write(0, "Var2")

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
    await mock_server.write(0, "Var2")

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
@pytest.mark.parametrize('expected_value', random.choices(range(1000), k=5))
async def test_server_on_change_write_server_from_async_cbk(
        mock_server: MockServer, opcua_client: asyncua.Client, expected_value: int
):
    await mock_server.write(0, "Var2")

    async def cbk(val):
        if val == 100:
            await mock_server.write(expected_value, "Var2")

    await mock_server.on_change(
        "Var2", cbk
    )

    await opcua_client.get_node("ns=1;i=10001").write_value(100)
    await mock_server.wait_for("Var2", expected_value, 1)

    assert (await mock_server.read("Var2")) == expected_value


@pytest.mark.asyncio
async def test_server_call_sync_function(mock_server: MockServer, opcua_client: asyncua.Client):
    q = queue.Queue()

    mock_server.on_call(
        "MyLittleFunction",
        lambda x, y, z: q.put((x, y, z)),
        arg_types=(int, int, float)
    )

    await mock_server.call("MyLittleFunction", 1, 2, 3.0)
    result = q.get(timeout=1)
    assert result == (1, 2, 3.0)


@pytest.mark.asyncio
async def test_server_call_async_function(mock_server: MockServer, opcua_client: asyncua.Client):
    q = asyncio.Queue()

    async def cbk(x, y, z):
        await q.put((x, y, z))

    mock_server.on_call(
        "MyLittleAsyncFunction",
        cbk,
        arg_types=(int, int, float)
    )

    await mock_server.call("MyLittleAsyncFunction", 1, 2, 3.0)
    result = await asyncio.wait_for(q.get(), 1)
    assert result == (1, 2, 3.0)


@pytest.mark.asyncio
async def test_server_call_wrong_arg_type(mock_server: MockServer, opcua_client: asyncua.Client):
    async def cbk(x, y, z):
        pass

    mock_server.on_call(
        "MyLittleAsyncFunctionWithStrictTypes",
        cbk,
        arg_types=(int, int, int)
    )

    with pytest.raises(TypeError):
        await mock_server.call("MyLittleAsyncFunctionWithStrictTypes", 1, 2, 3.0)


@pytest.mark.asyncio
async def test_server_call_ignoring_one_arg_type(mock_server: MockServer, opcua_client: asyncua.Client):
    q = asyncio.Queue()

    async def cbk(x, y, z):
        await q.put((x, y, z))

    mock_server.on_call(
        "MyLittleAsyncFunctionWithPartiallyStrictTypeCheck",
        cbk,
        arg_types=(int, int, None)
    )

    await mock_server.call("MyLittleAsyncFunctionWithPartiallyStrictTypeCheck", 1, 2, 3.0)
    result = await asyncio.wait_for(q.get(), 1)
    assert result == (1, 2, 3.0)


@pytest.mark.asyncio
async def test_server_call_ignoring_arg_types(mock_server: MockServer, opcua_client: asyncua.Client):
    q = asyncio.Queue()

    async def cbk(x, y, z):
        await q.put((x, y, z))

    mock_server.on_call(
        "MyLittleAsyncFunctionWithUnrestrictedTypeCheck",
        cbk,
        arg_types=None
    )

    await mock_server.call("MyLittleAsyncFunctionWithUnrestrictedTypeCheck", 1, 2, 3.0)
    result = await asyncio.wait_for(q.get(), 1)
    assert result == (1, 2, 3.0)


@pytest.mark.asyncio
async def test_server_call_write_server_from_callback(mock_server: MockServer, opcua_client: asyncua.Client):
    evt = asyncio.Event()

    async def cbk(x):
        await mock_server.write(x, "Var2")
        evt.set()

    mock_server.on_call(
        "MyLittleAsyncFunctionThatWritesServer",
        cbk,
        arg_types=None
    )

    await mock_server.call("MyLittleAsyncFunctionThatWritesServer", 102)
    await asyncio.wait_for(evt.wait(), 1)
    value = await mock_server.read("Var2")

    assert value == 102
