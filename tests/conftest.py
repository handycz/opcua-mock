import asyncio
import datetime
from unittest import mock

import asyncua
import pytest
from starlette.testclient import TestClient

from uamockapp.server import MockServer, DataImageItemValue, HistorySample
from uamockapp.web import create_web_interface


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
            await server.write("Var1", val)
            await server.write("Var2", val)
        await asyncio.sleep(0.1)

        yield server


@pytest.fixture(scope="module")
async def opcua_client():
    client = asyncua.Client("opc.tcp://localhost:4840")
    async with client:
        yield client


@pytest.fixture(scope="module")
async def web_app_client():
    mock_opcua_server = mock.Mock(
        get_data_image=mock.AsyncMock(
            return_value={
                "1:Var1": DataImageItemValue(
                    value=10,
                    history=[
                        HistorySample(
                            value=9,
                            timestamp=datetime.datetime.now()
                        )
                    ]
                )
            }
        ),
        get_function_list=mock.AsyncMock(
            return_value=[
              {
                "name": "RunWithNoArgs",
                "args": None
              },
              {
                "name": "AddTwoNumbers",
                "args": [
                  "float",
                  "float"
                ]
              }
            ]
        ),
        get_onchange_list=mock.AsyncMock(
            return_value=[
              {
                "var_name": "Var2",
                "history": [
                  {
                    "value": 11,
                    "timestamp": "2021-11-26T12:53:10.243374+00:00"
                  }
                ]
              },
              {
                "var_name": "Var1",
                "history": [
                  {
                    "value": 15,
                    "timestamp": "2021-11-26T12:53:10.243374+00:00"
                  }
                ]
              }
            ]
        )
    )

    app = create_web_interface(mock_opcua_server)
    return TestClient(app)
