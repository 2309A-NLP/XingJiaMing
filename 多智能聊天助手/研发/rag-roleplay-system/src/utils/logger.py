# -*- coding: utf-8 -*-  # 指定文件编码为 utf-8，确保中文日志内容不出现乱码
"""
统一结构化日志系统

本模块提供全系统统一的日志记录能力，解决"日志系统不统一"的问题。
核心设计原则是"一次配置，全局使用"。

设计特点：
1. 所有模块通过 get_logger(__name__) 获取 logger，名称自动反映模块路径
2. 日志自动写入三种目的地：文本文件、JSON 文件、控制台
3. ERROR 级别日志额外写入 error.log 便于问题排查
4. 按天轮转日志文件，保留 30 天历史，防止磁盘写满
5. JSON 结构化日志可直接对接 ELK/Grafana/Loki 等日志收集系统

使用方式：
    logger = get_logger(__name__)
    logger.info("系统启动完成")
    logger.error("数据库连接失败", exc_info=True)
"""

import logging       # Python 标准日志库，提供分级日志和处理器框架
import os             # 操作系统接口，用于文件路径和目录创建
import sys            # 系统模块，用于输出到控制台（stdout）
import json           # JSON 模块，用于结构化日志的序列化
from datetime import datetime  # 日期时间，用于日志中的时间戳
from logging.handlers import TimedRotatingFileHandler  # 按时间轮转的文件处理器
from ..config.settings import LOG_DIR  # 从配置中心获取日志目录路径

# 确保日志目录存在，若不存在则自动创建
# exist_ok=True 避免目录已存在时抛出 FileExistsError
os.makedirs(LOG_DIR, exist_ok=True)


# ======================== 文件路径 ========================
# 日志文件路径定义，所有日志集中存储在 LOG_DIR 目录下
TEXT_LOG = os.path.join(LOG_DIR, "app.log")          # 普通文本日志：人类可读的格式
JSON_LOG = os.path.join(LOG_DIR, "app.json.log")      # JSON 结构化日志：供 ELK/Grafana 等工具消费
ERROR_LOG = os.path.join(LOG_DIR, "error.log")        # 错误专用日志：只记录 ERROR 及以上级别


# ======================== 格式化器 ========================

class StructuredFormatter(logging.Formatter):
    """JSON 结构化日志格式化器

    继承标准库的 Formatter，将日志记录格式化为 JSON 字符串。
    相比纯文本日志，JSON 格式便于机器解析和日志分析工具处理。

    输出示例：
    {"timestamp": "2026-05-08T10:30:00.123456Z", "level": "INFO",
     "logger": "src.fastapi_app", "message": "服务启动成功", ...}
    """

    def format(self, record):
        """将日志记录格式化为 JSON 字符串

        Args:
            record: logging.LogRecord 对象，包含日志的所有信息

        Returns:
            str: JSON 格式的日志字符串
        """
        # 构建基础日志条目字典
        log_entry = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),  # ISO 8601 格式时间戳
            "level": record.levelname,       # 日志级别（INFO/ERROR/WARNING 等）
            "logger": record.name,           # Logger 名称（通常是模块名）
            "message": record.getMessage(),  # 格式化后的日志消息
            "module": record.module,         # 产生日志的模块名
            "function": record.funcName,     # 产生日志的函数名
            "line": record.lineno,           # 产生日志的行号
        }
        # 如果有异常信息，添加到日志条目中
        # exc_info 是一个三元组 (type, value, traceback)，有值时说明捕获了异常
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        # 如果有额外数据（通过 extra 参数传递），添加到日志条目中
        if hasattr(record, "extra_data"):
            log_entry["extra"] = record.extra_data
        # 序列化为 JSON 字符串，ensure_ascii=False 保留中文字符（而不是转义为 \u...）
        return json.dumps(log_entry, ensure_ascii=False)


# ======================== 日志格式 ========================
# 文本格式：包含时间、级别、模块位置和消息，方便阅读
# %(asctime)s 自动替换为时间，%(module)s:%(lineno)d 定位代码位置
TEXT_FORMAT = "[%(asctime)s] [%(levelname)s] [%(module)s:%(lineno)d] %(message)s"
# 控制台格式：更简洁，不含模块行号（终端空间有限）
CONSOLE_FORMAT = "[%(asctime)s] [%(levelname)s] %(message)s"
# 日期格式：年月日 时分秒
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# ======================== 全局统一处理器 ========================
# 使用全局标志避免重复挂载处理器（防止重复日志）
_handlers_attached = False


def _init_root_logger():
    """初始化 root logger，挂载所有处理器

    设计思路：不是给每个模块单独创建 logger 并配处理器，
    而是给 root logger 挂载处理器，所有子 logger 继承这些处理器。
    这样"一次配置，全局生效"，且日志格式完全统一。

    处理器列表：
    1. text_file —— 文本日志，INFO 级别，按天轮转，保留 30 天
    2. json_file —— JSON 结构化日志，INFO 级别，按天轮转，保留 30 天
    3. error_file —— 错误专用日志，ERROR 级别，按天轮转，保留 30 天
    4. console —— 控制台输出，INFO 级别

    按天轮转：每天午夜自动创建新日志文件，旧文件重命名为 app.log.YYYY-MM-DD
    """
    global _handlers_attached
    if _handlers_attached:  # 已初始化，跳过
        return
    _handlers_attached = True  # 标记为已初始化

    root = logging.getLogger()  # 获取 root logger
    root.setLevel(logging.INFO)  # 全局日志级别设为 INFO（低于 INFO 的 DEBUG 日志不记录）

    # 获取已存在的处理器名称集合，避免重复添加
    # 在 Uvicorn 热重载场景下会多次导入模块，此检查防止日志重复
    existing_names = {h.get_name() for h in root.handlers}

    # --- 文本日志处理器 (INFO 及以上) ---
    if "text_file" not in existing_names:
        h = TimedRotatingFileHandler(
            TEXT_LOG,            # 日志文件路径
            when="midnight",     # 每天午夜轮转
            interval=1,          # 轮转间隔为 1 天
            backupCount=30,      # 保留 30 天的历史文件
            encoding="utf-8"     # 编码格式
        )
        h.set_name("text_file")  # 设置处理器名称，用于去重
        h.setLevel(logging.INFO)  # 记录 INFO 及以上级别
        h.setFormatter(logging.Formatter(TEXT_FORMAT, DATE_FORMAT))  # 使用文本格式
        root.addHandler(h)

    # --- JSON 结构化日志处理器 (INFO 及以上) ---
    if "json_file" not in existing_names:
        h = TimedRotatingFileHandler(
            JSON_LOG,
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8"
        )
        h.set_name("json_file")
        h.setLevel(logging.INFO)
        h.setFormatter(StructuredFormatter())  # 使用 JSON 格式化器
        root.addHandler(h)

    # --- 错误专用日志处理器 (ERROR 及以上) ---
    # 独立的错误文件便于运维人员快速查看错误
    if "error_file" not in existing_names:
        h = TimedRotatingFileHandler(
            ERROR_LOG,
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8"
        )
        h.set_name("error_file")
        h.setLevel(logging.ERROR)  # 只记录 ERROR 及以上级别（包括 CRITICAL）
        h.setFormatter(logging.Formatter(TEXT_FORMAT, DATE_FORMAT))
        root.addHandler(h)

    # --- 控制台输出处理器 ---
    # 在终端 stdout 输出，便于开发调试和 Docker 日志收集
    if "console" not in existing_names:
        h = logging.StreamHandler(sys.stdout)  # 输出到标准输出
        h.set_name("console")
        h.setLevel(logging.INFO)
        h.setFormatter(logging.Formatter(CONSOLE_FORMAT, DATE_FORMAT))
        root.addHandler(h)


def get_logger(name: str = __name__) -> logging.Logger:
    """获取统一配置的 logger

    所有模块通过此函数获取 logger，用法：
        logger = get_logger(__name__)
        logger.info("这是一个信息日志")
        logger.error("这是一个错误日志", exc_info=True)  # exc_info 输出异常堆栈

    Args:
        name: logger 名称，通常传入 __name__，会显示为模块的完整路径

    Returns:
        logging.Logger: 配置好的 logger 实例
    """
    _init_root_logger()  # 确保 root logger 已初始化（幂等操作）
    return logging.getLogger(name)  # 返回指定名称的子 logger


def log_request(method: str, path: str, status: int, duration_ms: float,
                user_id: str = "-"):
    """记录 API 请求日志

    专门用于记录 HTTP 请求的相关信息，同时写入文本和 JSON 格式。

    Args:
        method: HTTP 方法（GET/POST/DELETE 等）
        path: 请求路径（如 /api/chat/send）
        status: HTTP 状态码（200/401/500 等）
        duration_ms: 请求处理耗时（毫秒）
        user_id: 用户标识（默认为 "-" 表示未登录）
    """
    logger = get_logger("api.request")  # 使用 api.request 分类名称
    logger.info(
        f"REQUEST {method} {path} -> {status} ({duration_ms:.0f}ms) [user={user_id}]",
        extra={"extra_data": {     # 额外结构化数据（会出现在 JSON 日志中）
            "type": "request",      # 日志类型：请求日志
            "method": method,       # HTTP 方法
            "path": path,           # 请求路径
            "status": status,       # 响应状态码
            "duration_ms": round(duration_ms, 2),  # 耗时（保留 2 位小数）
            "user_id": user_id,     # 用户 ID
        }}
    )


# 模块导入时自动初始化 root logger
# 这样在旧代码直接引用此模块的 logger 时可以正常工作
_init_root_logger()
# 默认 logger 实例，供其他模块通过 from src.utils.logger import logger 直接使用
logger = logging.getLogger("RAG_SYSTEM")
