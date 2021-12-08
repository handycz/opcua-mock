import asyncio
import logging
from threading import Thread
from typing import List, Dict

import uvicorn
from fastapi import FastAPI, APIRouter, HTTPException

from uamockapp.server import MockServer, OnChangeDescription, FunctionDescription, DataImageItemValue

__all__ = ["create_web_interface"]


def create_web_interface(opcua: MockServer) -> FastAPI:
    router = APIRouter()
    logger = logging.getLogger(__name__)

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

    @router.post("/call/{function_name}")
    async def call_function(function_name: str, parameters: List[str]):
        try:
            await opcua.call(function_name, *parameters, auto_cast_types=True)
        except ValueError as e:
            logger.error("Error when calling function", e)
            raise HTTPException(status_code=404, detail="Unknown callable")
        except TypeError as e:
            logger.error("Wrong parameters provided", e)
            raise HTTPException(status_code=406, detail="Wrong parameter types or length")

        return {"status": "ok"}

    app = FastAPI()
    app.include_router(router, prefix="/api")

    return app
