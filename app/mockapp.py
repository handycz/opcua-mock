import asyncio
import logging
import argparse
from collections import Coroutine, Callable
from typing import Any, Tuple

import hypercorn
import hypercorn.asyncio
from asyncio import Task

from app.web import create_web_interface
from app.scanner import generate_server_config
from app.server import MockServer

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def mockapp(server_initialization: Callable[[MockServer], Coroutine[Any, Any, None]] = None) -> None:
    args = await get_args()
    if "scan" in args and args["scan"] is not None:
        await generate_server_config(args["scan"], args["config"])
    else:
        server, app_task = await start_app(args["config"], args["http_port"])
        if server_initialization is not None:
            await server_initialization(server)

        await app_task


async def start_app(config_path: str, http_port: int) -> Tuple[MockServer, Task]:
    mockserver = MockServer(config_path)
    await mockserver.init()
    await mockserver.start()

    webapp = create_web_interface(mockserver)
    webserver_config = hypercorn.Config()
    webserver_config.bind = [f"localhost:{http_port}"]
    web_task = asyncio.create_task(
        hypercorn.asyncio.serve(
            webapp, webserver_config
        )
    )
    # uvicorn.run(webapp, host="localhost", port=http_port)
    # webserver_thread = Thread(target=lambda: uvicorn.run(webapp, host="localhost", port=http_port))
    # webserver_thread.start()

    return mockserver, web_task


async def get_args():
    all_args = argparse.ArgumentParser()

    all_args.add_argument("-s", "--scan")
    all_args.add_argument("-c", "--config", required=True, help="path/to/my-config.yaml")
    all_args.add_argument("-p", "--http-port", required=False, nargs="?", const=8080, type=int)

    return all_args.parse_args().__dict__


if __name__ == "__main__":
    asyncio.run(mockapp())
