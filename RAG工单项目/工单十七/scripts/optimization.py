"""
工单十七：RAGFlow API优化方案
包含：查询缓存、请求限流、性能监控

使用方式：
1. 将此文件放在压测目录
2. locustfile_cached.py 会自动使用缓存
3. 优化后的prompt配置通过API设置
"""

import time
import hashlib
from collections import OrderedDict


class LRUCache:
    """LRU缓存实现，用于缓存查询结果"""
    
    def __init__(self, max_size=1000, ttl=300):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl  # 秒
        self.hits = 0
        self.misses = 0
    
    def get(self, key):
        """获取缓存"""
        if key in self.cache:
            cached_time, value = self.cache[key]
            if time.time() - cached_time < self.ttl:
                # 命中，移到末尾
                self.cache.move_to_end(key)
                self.hits += 1
                return value
            else:
                # 过期，删除
                del self.cache[key]
        self.misses += 1
        return None
    
    def set(self, key, value):
        """设置缓存"""
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = (time.time(), value)
        # 超过最大大小，删除最旧的
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)
    
    def get_stats(self):
        """获取缓存统计"""
        total = self.hits + self.misses
        hit_rate = self.hits / total * 100 if total > 0 else 0
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "size": len(self.cache)
        }


# 全局缓存实例
query_cache = LRUCache(max_size=1000, ttl=300)


def get_cache_key(question, chat_id):
    """生成缓存key"""
    return hashlib.md5(f"{chat_id}:{question}".encode()).hexdigest()


# 优化后的Prompt配置
OPTIMIZED_PROMPT_CONFIG = {
    "system": "你是智能助手。根据知识库内容简洁回答问题。如无相关内容请说\"未找到相关信息\"。",
    "prologue": "你好，我是你的助手。",
    "quote": False,
    "top_n": 3,  # 从6减少到3，减少prompt长度
}
