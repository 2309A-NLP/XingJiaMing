"""工单十三 - RAG 性能瓶颈识别与优化 API。"""
from __future__ import annotations

import logging
import threading

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI(title="RAG 性能优化系统 - 工单十三", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger.info("%s %s", request.method, request.url.path)
        response = await call_next(request)
        if response.status_code >= 400:
            logger.warning("%s %s -> %d", request.method, request.url.path, response.status_code)
        return response


app.add_middleware(LoggingMiddleware)

from scripts.middleware.rate_limiter import RateLimitMiddleware

app.add_middleware(RateLimitMiddleware)

from api.routes import api_router

app.include_router(api_router)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("未处理异常: %s %s -> %s", request.method, request.url.path, str(exc), exc_info=True)
    from fastapi.responses import JSONResponse

    if isinstance(exc, ValueError):
        return JSONResponse(status_code=400, content={"error": str(exc), "type": "validation"})
    if isinstance(exc, TimeoutError):
        return JSONResponse(status_code=504, content={"error": "请求超时", "type": "timeout"})
    return JSONResponse(
        status_code=500,
        content={"error": "服务器内部错误", "type": "internal", "detail": str(exc)[:200]},
    )


@app.on_event("startup")
async def on_startup():
    from scripts.logger import setup_logging

    setup_logging()
    logger.info("日志系统启动")

    def _preload():
        try:
            logger.info("预加载工单十三组件...")
            from api.init import get_components

            get_components()
            logger.info("工单十三组件预加载完成")
        except Exception as e:
            logger.error("预加载失败: %s", e)

    threading.Thread(target=_preload, daemon=True).start()
