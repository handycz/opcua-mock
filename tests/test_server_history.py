import pytest

from app.server import MockServer


@pytest.mark.asyncio
async def test_history_server_read_node_history_default_count(history_mock_server: MockServer):
    raw_values = await history_mock_server.read_history("Var1")
    values = [value.value for value in raw_values]

    assert list(reversed(range(5, 15))) == values


@pytest.mark.asyncio
async def test_history_server_read_node_history_count_by_config(history_mock_server: MockServer):
    raw_values = await history_mock_server.read_history("Var2")
    values = [value.value for value in raw_values]

    assert list(reversed(range(15))) == values
