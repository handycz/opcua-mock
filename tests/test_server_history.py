import datetime
from typing import List

import pytest

from uamockapp.server import MockServer


@pytest.mark.asyncio
async def test_history_server_read_node_history_default_count(history_mock_server: MockServer):
    raw_values = await history_mock_server.read_history("Var1")
    values = [value.value for value in raw_values]

    assert values == list(reversed(range(5, 15)))


@pytest.mark.asyncio
async def test_history_server_read_node_history_count_by_config(history_mock_server: MockServer):
    raw_values = await history_mock_server.read_history("Var2")
    values = [value.value for value in raw_values]

    assert values == list(reversed(range(15)))


@pytest.mark.asyncio
async def test_history_server_read_node_history_timestamps(history_mock_server: MockServer):
    raw_values = await history_mock_server.read_history("Var1", num_values=5)
    values: List[datetime] = [value.timestamp for value in raw_values]
    current_time = datetime.datetime.now(tz=datetime.timezone.utc)

    assert all(
        map(
            lambda val: (current_time - val) < datetime.timedelta(minutes=1),
            values
        )
    )
