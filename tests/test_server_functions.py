import asyncio
import queue

import asyncua
import pytest

from uamockapp.server import MockServer


@pytest.mark.asyncio
async def test_server_call_sync_function(mock_server: MockServer, opcua_client: asyncua.Client):
    q = queue.Queue()

    await mock_server.on_call(
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

    await mock_server.on_call(
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

    await mock_server.on_call(
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

    await mock_server.on_call(
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

    await mock_server.on_call(
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
        await mock_server.write("Var2", x)
        evt.set()

    await mock_server.on_call(
        "MyLittleAsyncFunctionThatWritesServer",
        cbk,
        arg_types=None
    )

    await mock_server.call("MyLittleAsyncFunctionThatWritesServer", 102)
    await asyncio.wait_for(evt.wait(), 1)
    value = await mock_server.read("Var2")

    assert value == 102
