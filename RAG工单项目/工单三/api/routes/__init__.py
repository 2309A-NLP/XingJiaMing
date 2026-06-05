"""路由模块"""
from fastapi import APIRouter
from .health import router as health_router
from .query import router as query_router
from .chat import router as chat_router
from .translate import router as translate_router
from .ingest import router as ingest_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(query_router)
api_router.include_router(chat_router)
api_router.include_router(translate_router)
api_router.include_router(ingest_router)