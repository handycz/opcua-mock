import asyncio
from threading import Thread
from typing import List, Dict

import uvicorn
from fastapi import FastAPI, APIRouter

from app.server import MockServer, OnChangeDescription, FunctionDescription, DataImageItemValue


def create_web_interface(opcua: MockServer) -> FastAPI:
    router = APIRouter()

    @router.get("/data", response_model=Dict[str, DataImageItemValue])
    async def get_data():
        return await opcua.get_data_image()

    @router.get("/function", response_model=List[FunctionDescription])
    async def list_functions():
        function_list = await opcua.get_function_list()
        return function_list

    @router.get("/watched", response_model=List[OnChangeDescription])
    async def list_watched():
        return await opcua.get_onchange_list()

        # return OnchangeDescriptionItemModel.parse_obj(
        #     await opcua.get_onchange_list()
        # )

    app = FastAPI()
    app.include_router(router, prefix="/api")

    return app


async def create_server():
    server = MockServer("config.yaml")
    await server.init()
    await server.start()
    await server.on_call("CallMe", lambda: print("Hi!"))
    await server.on_call("CallMe2", lambda x: print("Hi, ", x), arg_types=[str, MockServer])
    await server.on_call("CallMe3", lambda: print("Hi!"), None)
    await server.on_change("Var1", lambda _: None)
    await server.on_change("Var2", lambda _: None)

    return server


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    server = loop.run_until_complete(create_server())
    app = create_web_interface(server)
    Thread(target=loop.run_forever).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
    loop.run_until_complete(server.stop)
