import asyncio
import logging

from server import MockServer

logging.basicConfig(level=logging.DEBUG)

async def main():
    server = MockServer("config.yaml")
    await server.init()
    print(await server.read("MyVar"))
    await server.write(1111, "Yoursxar")
    print(await server.read("YoursVar"))
    async with server._server:
        await asyncio.sleep(10000)

asyncio.run(main())
