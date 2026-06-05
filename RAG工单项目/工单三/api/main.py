"""工单3 - RAG智能问答系统 API

工单编号：人工智能+NLP-RAG+基于 PDF 文档的问答系统

功能：
- Query 理解（意图识别、消歧、分解与抽象）
- 向量检索 + BM25 双路召回
- LLM 生成回答
- 对话管理
"""
from __future__ import annotations
import logging
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv(override=True)
logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(title='RAG 智能问答系统 - 工单3', version='2.0.0')

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 日志中间件
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger.info('%s %s', request.method, request.url.path)
        response = await call_next(request)
        if response.status_code >= 400:
            logger.warning('%s %s -> %d', request.method, request.url.path, response.status_code)
        return response


app.add_middleware(LoggingMiddleware)

# 限流中间件：每 IP 每秒最大 10 次请求
from scripts.middleware.rate_limiter import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)


# 注册路由
from api.routes import api_router
app.include_router(api_router)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error('未处理异常: %s %s -> %s', request.method, request.url.path, str(exc), exc_info=True)
    from fastapi.responses import JSONResponse
    if isinstance(exc, ValueError):
        return JSONResponse(status_code=400, content={'error': str(exc), 'type': 'validation'})
    if isinstance(exc, TimeoutError):
        return JSONResponse(status_code=504, content={'error': '请求超时', 'type': 'timeout'})
    return JSONResponse(status_code=500, content={'error': '服务器内部错误', 'type': 'internal', 'detail': str(exc)[:200]})


# 启动事件
@app.on_event('startup')
async def on_startup():
    from scripts.logger import setup_logging
    setup_logging()
    logger.info('日志系统启动')

    # 后台预加载模型，避免首次请求卡顿
    def _preload():
        try:
            logger.info('预加载模型...')
            from api.components import get_components
            get_components()
            logger.info('预加载完成')
        except Exception as e:
            logger.error('预加载失败: %s', e)

    threading.Thread(target=_preload, daemon=True).start()