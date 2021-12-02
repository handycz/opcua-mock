import asyncio

from app.mockapp import mockapp
from app.server import MockServer


async def init_function(mock: MockServer):
    async def simulate_robot_run(value: bool):
        if not value:
            return

        await mock.write("Running", "Robot/Status")
        num_parts = await mock.read("Tray/NumParts")
        if num_parts > 0:
            await asyncio.sleep(2)
            await mock.write(num_parts - 1, "Tray/NumParts")
            await mock.write("Idle", "Robot/Status")
        else:
            await mock.write("Error", "Robot/Status")

    async def simulate_manual_tray_fill():
        await mock.write(10, "Tray/NumParts")
        await mock.write("Idle", "Robot/Status")

    await mock.on_change(
        "Robot/Start",
        simulate_robot_run,
    )

    await mock.on_call(
        "FillTray",
        simulate_manual_tray_fill
    )

asyncio.run(
    mockapp(server_initialization=init_function)
)

