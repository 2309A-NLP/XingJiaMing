"""请求限流中间件 - 只限流写操作"""
from __future__ import annotations
import time
import threading
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: float = 1.0):
        self._max = max_requests
        self._window = window_seconds
        self._records = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            self._records[key] = [t for t in self._records[key] if now - t < self._window]
            if len(self._records[key]) >= self._max:
                return False
            self._records[key].append(now)
            return True


_limiter = RateLimiter(max_requests=20, window_seconds=1.0)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 只对 /api 下的写操作限流，GET/HEAD/OPTIONS 不限
        if not request.url.path.startswith('/api/'):
            return await call_next(request)
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return await call_next(request)
        client_ip = request.client.host if request.client else 'unknown'
        if not _limiter.is_allowed(client_ip):
            return JSONResponse(
                status_code=429,
                content={'error': '请求过于频繁，请稍后重试', 'type': 'rate_limit'}
            )
        return await call_next(request)
