"""查询缓存模块

相同问题直接返回缓存结果，避免重复调用 API
缓存策略：TTL 300秒，最多200条，LRU淘汰
"""
import time
from typing import Optional, Any

_query_cache: dict = {}
_CACHE_TTL = 300  # 缓存 5 分钟


def get_cache_key(question: str, top_k: int, language: str) -> str:
    """生成缓存 key"""
    return f"{question.strip().lower()}|{top_k}|{language}"


def cache_get(key: str) -> Optional[Any]:
    """获取缓存，过期返回 None"""
    entry = _query_cache.get(key)
    if entry and time.time() - entry['ts'] < _CACHE_TTL:
        return entry['data']
    return None


def cache_set(key: str, data: Any) -> None:
    """写入缓存，超限时淘汰最旧的"""
    _query_cache[key] = {'data': data, 'ts': time.time()}
    if len(_query_cache) > 200:
        oldest = min(_query_cache, key=lambda k: _query_cache[k]['ts'])
        del _query_cache[oldest]