import asyncio

from uamockapp.mockapp import mockapp
from uamockapp.server import MockServer


async def init_function(mock: MockServer):
    async def simulate_robot_run(value: bool):
        if not value:
            return

        await mock.write("Robot/Status", "Running")
        num_parts = await mock.read("Tray/NumParts")
        if num_parts > 0:
            await asyncio.sleep(2)
            await mock.write("Tray/NumParts", num_parts - 1)
            await mock.write("Robot/Status", "Idle")
        else:
            await mock.write("Robot/Status", "Error")

    async def simulate_manual_tray_fill():
        await mock.write("Tray/NumParts", 10)
        await mock.write("Robot/Status", "Idle")

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

