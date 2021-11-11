import asyncio

import asyncua
import pytest


from app.server import MockServer


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def mock_server():
    server = MockServer(
        "test_server_config.yaml"
    )

    await server.init()
    async with server:
        yield server


@pytest.fixture(scope="module")
async def history_mock_server():
    server = MockServer(
        "test_server_config.yaml"
    )

    await server.init()
    async with server:
        for val in range(15):
            await server.write(val, "Var1")
            await server.write(val, "Var2")

        yield server


@pytest.fixture(scope="module")
async def opcua_client():
    client = asyncua.Client("opc.tcp://localhost:4840")
    async with client:
        yield client
