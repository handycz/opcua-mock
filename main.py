import asyncio
import logging

from server import MockServer

logging.basicConfig(level=logging.DEBUG)

async def main():
    server = MockServer("config.yaml")
    await server.init()
    print(await server.read("MyVar"))
    await server.write(1111, "YoursVar")
    print(await server.read("Yoursvar"))

asyncio.run(main())
