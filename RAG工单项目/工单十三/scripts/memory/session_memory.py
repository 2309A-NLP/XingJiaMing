"""Redis 短期记忆 - 存储最近几轮对话给 LLM 当上下文"""
import json
import logging
import os
from typing import List

logger = logging.getLogger(__name__)


class SessionMemory:
    """用 Redis 存最近 N 轮对话，给 LLM 提供上下文。"""

    def __init__(self, host=None, port=None, max_turns=10, ttl=3600):
        """max_turns: 最多保留几轮对话; ttl: 过期时间（秒）。"""
        import redis

        host = host or os.getenv("REDIS_HOST", "localhost")
        port = int(port or os.getenv("REDIS_PORT", "6379"))
        password = os.getenv("REDIS_PASSWORD") or None
        db = int(os.getenv("REDIS_DB", "0"))

        self._r = redis.Redis(
            host=host,
            port=port,
            password=password,
            db=db,
            decode_responses=True,
        )
        self._max = max_turns * 2  # 每轮=user+assistant
        self._ttl = ttl
        try:
            self._r.ping()
            logger.info("Redis 连接成功: %s:%s db=%s", host, port, db)
        except Exception as e:
            logger.warning("Redis 不可用，短期记忆将跳过: %s", e)
            self._r = None

    def _key(self, chat_id: str) -> str:
        return f"chat:{chat_id}:history"

    def add(self, chat_id: str, role: str, content: str):
        """追加一条消息到会话历史。"""
        if not self._r:
            return
        key = self._key(chat_id)
        msg = json.dumps({"role": role, "content": content}, ensure_ascii=False)
        self._r.rpush(key, msg)
        self._r.ltrim(key, -self._max, -1)  # 只保留最近 N 条
        self._r.expire(key, self._ttl)

    def get_history(self, chat_id: str) -> List[dict]:
        """获取最近几轮对话历史，给 LLM 当上下文用。"""
        if not self._r:
            return []
        key = self._key(chat_id)
        items = self._r.lrange(key, 0, -1)
        return [json.loads(i) for i in items]

    def clear(self, chat_id: str):
        """清空某个对话的短期记忆。"""
        if not self._r:
            return
        self._r.delete(self._key(chat_id))
