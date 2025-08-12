"""
API v1 router
"""
from fastapi import APIRouter

from .endpoints import tasks, files, websocket, callbacks
from . import config

api_router = APIRouter()

api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(websocket.router, prefix="/ws", tags=["websocket"])
api_router.include_router(callbacks.router, prefix="/callbacks", tags=["callbacks"])
api_router.include_router(config.router, prefix="/config", tags=["configuration"])