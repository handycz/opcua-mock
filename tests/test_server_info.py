import asyncio
import pytest

from app.server import MockServer


@pytest.mark.asyncio
async def test_server_read_data_image(mock_server: MockServer):
    data = await mock_server.get_data_image()
    expected = dict({
        '1:Var1': 15,
        '1:Var2': 11,
        '1:Obj/2:Var3': 101
    })

    assert data == expected


@pytest.mark.asyncio
async def test_server_list_functions(mock_server: MockServer):
    await mock_server.on_call(
        "RunRobotThreeArgs", lambda: None, (int, int, str)
    )

    functions1 = await mock_server.get_function_list()

    await mock_server.on_call(
        "StopRobotNoArg", lambda: None
    )

    functions2 = await mock_server.get_function_list()

    assert len(functions1) == 1
    assert len(functions2) == 2

    assert functions1[0].name == "RunRobotThreeArgs"
    assert functions1[0].args == [int, int, str]

    assert functions2[0].name == "RunRobotThreeArgs"
    assert functions2[0].args == [int, int, str]

    assert functions2[1].name == "StopRobotNoArg"
    assert functions2[1].args is None


@pytest.mark.asyncio
async def test_server_onchange_list(mock_server: MockServer):
    for val in range(5):
        await mock_server.write(val, "Var1")
        await mock_server.write(val * 2, "Var2")

    await asyncio.sleep(0.1)

    await mock_server.on_change(
        "Var1", lambda: None, int
    )
    onchange1 = await mock_server.get_onchange_list()

    await mock_server.on_change(
        "Var2", lambda: None
    )
    onchange2 = await mock_server.get_onchange_list()

    assert len(onchange1) == 1
    assert len(onchange2) == 2

    assert onchange1[0].var_name == "Var1"
    assert [sample.value for sample in onchange1[0].history] == [4, 3, 2, 1, 0, 15]

    assert onchange2[0].var_name == "Var1"
    assert [sample.value for sample in onchange2[0].history] == [4, 3, 2, 1, 0, 15]

    assert onchange2[1].var_name == "Var2"
    assert [sample.value for sample in onchange2[1].history] == [8, 6, 4, 2, 0, 11]
