import pytest
from starlette.testclient import TestClient
from utils import assert_json_equal


@pytest.mark.asyncio
async def test_web_server_data_image(web_app_client: TestClient):
    response = web_app_client.get("/api/data")
    assert_json_equal(
        response.json(),
        {
            "1:Var1": {
                "history": [
                    {
                        "timestamp": ...,
                        "value": 9
                    }
                ],
                "value": 10
            }
        }
    )


@pytest.mark.asyncio
async def test_web_server_list_functions(web_app_client: TestClient):
    response = web_app_client.get("/api/function")
    assert_json_equal(
        response.json(),
        [
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
    )


@pytest.mark.asyncio
async def test_web_server_list_functions(web_app_client: TestClient):
    response = web_app_client.get("/api/watched")
    assert_json_equal(
        response.json(),
        [
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
