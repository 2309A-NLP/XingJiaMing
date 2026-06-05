# -*- coding: utf-8 -*-  # 指定文件编码为utf-8，确保中文字符能正常处理
"""
Redis 缓存操作模块

本模块提供以下功能：
1. Redis 客户端连接管理（延迟初始化）
2. 聊天记录的短期存储（用于对话上下文）
3. 聊天记录的读取和清理

Redis 作为短期记忆存储的优势：
- 高性能读写，适合频繁访问的会话数据
- 支持自动过期，无需手动清理过期会话
- 支持列表结构，适合存储有序的对话历史

技术栈：
- redis-py: Redis Python 客户端库
"""

import redis  # Redis 官方 Python 客户端，提供同步的 Redis 操作接口
from ..config.settings import REDIS_CONFIG  # 从配置模块导入 Redis 连接参数（host/port/db）

# ==================== Redis 客户端管理 ====================
redis_client = None  # 全局 Redis 客户端实例，初始为 None，首次使用时才创建（延迟初始化模式）

def get_redis_client():
    """
    获取 Redis 客户端连接

    使用延迟初始化模式（Lazy Initialization），只在首次调用时才创建连接，
    避免模块加载时 Redis 还未启动导致导入失败的问题。

    Returns:
        redis.Redis: Redis 客户端实例
    """
    global redis_client  # 声明使用全局变量
    if redis_client is None:  # 仅在首次调用时创建连接
        # 创建 Redis 客户端，所有参数从配置中心读取
        redis_client = redis.Redis(
            host=REDIS_CONFIG["host"],                          # Redis 服务器地址（默认 localhost）
            port=REDIS_CONFIG["port"],                          # Redis 端口（默认 6379）
            db=REDIS_CONFIG["db"],                              # 使用的数据库编号（默认 0）
            decode_responses=REDIS_CONFIG["decode_responses"]   # 自动解码为字符串（True 避免 bytes 类型）
        )
    return redis_client  # 返回客户端实例（首次调用后始终复用同一个连接）


# ==================== 键名生成 ====================
def get_chat_key(user_id, character_id):
    """
    生成聊天记录的 Redis 键名

    键名规则为 "chat:{user_id}:{character_id}"，通过冒号分隔实现命名空间隔离。
    这种命名方式的好处是：
    - 所有聊天记录集中在 chat: 前缀下，便于管理和清理
    - 可以按 user_id 或 character_id 进行模式匹配（KEYS 或 SCAN）

    Args:
        user_id: 用户ID（数字）
        character_id: 角色ID（字符串，如 "lawyer"）

    Returns:
        str: Redis 键名
    """
    return f"chat:{user_id}:{character_id}"


# ==================== 聊天记录管理 ====================
def save_message(user_id, character_id, role, content):
    """
    保存一条聊天记录到 Redis（短期记忆）

    聊天记录以列表（List）形式存储在 Redis 中，每条消息格式为 "role:content"。
    使用列表的原因：支持按时间顺序存储和读取，且 rpush/lrange 操作都是 O(1) 复杂度。

    同时控制列表长度（只保留最近 N 轮对话），并设置 5 分钟过期时间来自动清理空闲会话。

    Args:
        user_id: 用户ID
        character_id: 角色ID
        role: 消息角色（"user" 或 "assistant"）
        content: 消息内容（文本）
    """
    try:
        # 1. 生成该用户与该角色之间的聊天记录键名
        key = get_chat_key(user_id, character_id)

        # 2. 将消息格式化为 "角色:内容" 的字符串形式，便于解析
        #    使用冒号分隔，因为 role 不包含冒号，可以用 split(":", 1) 还原
        message = f"{role}:{content}"

        # 3. 将消息推入列表的末尾（rpush = right push），保持时间顺序
        get_redis_client().rpush(key, message)

        # 4. 控制列表长度，只保留最后 N 条消息
        #    history_limit 默认为 5 轮对话，每轮有 user+assistant 两条消息，所以乘以 2
        limit = REDIS_CONFIG.get("history_limit", 5) * 2
        #    ltrim 保留列表中最后 limit 个元素（-limit 表示倒数第 limit 个到末尾）
        get_redis_client().ltrim(key, -limit, -1)

        # 5. 设置键的过期时间为 300 秒（5 分钟）
        #    这是 TTL（Time-To-Live）机制，如果用户 5 分钟内没有新对话，自动清理
        #    避免 Redis 中堆积大量已结束会话的聊天记录
        get_redis_client().expire(key, 300)

    except Exception as e:
        # 兜底异常捕获，防止 Redis 异常影响主业务流程
        from src.utils.logger import logger  # 延迟导入避免循环依赖
        logger.error(f"保存Redis聊天记录异常：{e}")


def get_history(user_id, character_id):
    """
    获取用户与特定角色的最近聊天记录

    从 Redis 列表中读取所有消息，解析后拼接到大模型的 Prompt 中作为对话上下文。
    历史记录让 LLM 能够"记住"之前的对话内容，实现多轮对话的连贯性。

    Args:
        user_id: 用户ID
        character_id: 角色ID

    Returns:
        str: 格式化的对话历史文本，格式为 "用户：xxx\n助手：xxx\n..."
              空字符串表示无历史记录
    """
    try:
        # 1. 生成对应的 Redis 键名
        key = get_chat_key(user_id, character_id)

        # 2. 获取列表中所有元素（lrange 0 -1 表示从第一个到最后一个）
        messages = get_redis_client().lrange(key, 0, -1)

        # 3. 遍历解析每条消息
        history = []
        for msg in messages:
            try:
                # 每条消息存储格式为 "role:content"，用 split(":", 1) 分割
                # 第二个参数 1 表示只分割第一个冒号，避免 content 中的冒号干扰
                if ":" in msg:
                    role, content = msg.split(":", 1)
                    # 将英文角色标识转为中文，用于构建可读的对话上下文
                    role_cn = "用户" if role == "user" else "助手"
                    history.append(f"{role_cn}：{content}")
            except Exception as msg_error:
                # 单条消息解析失败不影响其他消息
                from src.utils.logger import logger
                logger.error(f"解析聊天记录异常：{msg_error}")
                continue

        # 4. 用换行符拼接所有消息，形成对话文本块
        return "\n".join(history)

    except Exception as e:
        # 任何异常都返回空字符串，保证调用方逻辑不中断
        from src.utils.logger import logger
        logger.error(f"获取Redis聊天记录异常：{e}")
        return ""


def clear_history(user_id, character_id):
    """
    清空某个用户与特定角色的聊天记录

    当用户点击"清空记录"按钮时调用，删除 Redis 中对应的键。

    Args:
        user_id: 用户ID
        character_id: 角色ID
    """
    try:
        # 生成键名并删除
        key = get_chat_key(user_id, character_id)
        get_redis_client().delete(key)

    except Exception as e:
        from src.utils.logger import logger
        logger.error(f"清空Redis聊天记录异常：{e}")
