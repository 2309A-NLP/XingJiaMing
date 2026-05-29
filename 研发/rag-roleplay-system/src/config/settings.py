# -*- coding: utf-8 -*-  # 指定文件编码为 utf-8，防止中文注释乱码

import os  # os 模块：用于读取环境变量和拼接文件路径
from dotenv import load_dotenv  # python-dotenv 库：将 .env 文件中的键值对加载为环境变量

# 加载 .env 文件中的配置到环境变量
# .env 文件包含敏感信息（API密钥、数据库密码等），不提交到 Git 仓库
# 这样可以在不同部署环境中使用不同的 .env 文件，实现配置与代码分离
load_dotenv()


# ====================== 基础路径配置 ======================
# BASE_DIR: 项目根目录路径
# 通过 __file__ 获取当前文件路径，然后向上两级得到项目根目录
# config/settings.py -> config/ -> 项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# DATA_DIR: 存放 PDF 原始数据集的目录
# 用于存储法律条文、医疗知识等文档，供知识库构建使用
DATA_DIR = os.path.join(BASE_DIR, "data", "PDF数据集")

# LOG_DIR: 日志输出目录
# 系统运行日志和错误日志都集中存储在此目录下
LOG_DIR = os.path.join(BASE_DIR, "logs")


# ====================== 模型配置 ======================
# MODEL_PATH: 各 AI 模型的本地路径
# 所有模型都在本地加载运行，不依赖外部 API（除了 LLM 使用远程 API）
# 路径可通过环境变量覆盖，默认为 Windows 开发环境路径（后续部署需修改）
MODEL_PATH = {
    "embedding": os.getenv("EMBEDDING_MODEL_PATH", r"D:\AI_models\BGE-M3"),          # BGE-M3 文本嵌入模型
    "rerank": os.getenv("RERANK_MODEL_PATH", r"D:\AI_models\bge-reranker-base"),    # BGE-Reranker 重排序模型
    "llm": os.getenv("LLM_MODEL_PATH", "")                                           # LLM 本地模型路径（当前未使用）
}


# ====================== LLM推理配置 ======================
# LLM_CONFIG: 大语言模型 API 调用配置
# 默认使用 DeepSeek API，兼容 OpenAI SDK 格式
LLM_CONFIG = {
    "engine": "deepseek",                                    # LLM 引擎类型
    "api_key": os.getenv("API_KEY", ""),                    # API 密钥（从 .env 读取，必填）
    "api_url": os.getenv("API_URL", "https://api.deepseek.com"),  # API 地址
    "model": "deepseek-v4-flash",                           # 模型名称（DeepSeek V4 Flash）
    "temperature": 0.7,                                      # 生成温度（0-1），越高越有创造性
    "top_p": 0.8,                                           # Top-p 采样参数
    "max_tokens": 1024,                                      # 单次生成最大 token 数
    "timeout": 60                                            # API 请求超时时间（秒）
}


# ====================== Milvus 向量库 ======================
# MILVUS_CONFIG: 向量数据库连接和集合配置
# Milvus 负责存储文档向量并执行相似性搜索
MILVUS_CONFIG = {
    "host": os.getenv("MILVUS_HOST", "192.168.72.128"),     # Milvus 服务器地址（你的虚拟机）
    "port": int(os.getenv("MILVUS_PORT", "19530")),          # Milvus gRPC 端口（默认 19530）
    "collection_name": "law_rag",                            # 法律知识库集合名（存储本案案卷）
    "memory_collection": "long_memory",                      # 长期记忆集合名（存储历史对话摘要）
    "dim": 1024,                                             # 向量维度（必须与 BGE-M3 输出维度一致）
    "top_k": 10                                              # 初始召回数量（Rerank 前保留）
}


# ====================== Redis 短期记忆 ======================
# REDIS_CONFIG: Redis 缓存数据库连接配置
# Redis 存储短期对话历史，支持自动过期，实现高性能读取
REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "localhost"),            # Redis 服务器地址（本机）
    "port": int(os.getenv("REDIS_PORT", "6379")),            # Redis 端口（默认 6379）
    "db": int(os.getenv("REDIS_DB", "0")),                  # 数据库编号（默认 0）
    "decode_responses": True,                                # 自动解码为字符串（避免手动处理 bytes）
    "history_limit": 5                                       # 保留最近 5 轮对话（共 10 条消息）
}


# ====================== MySQL 用户/对话存储 ======================
# MYSQL_CONFIG: MySQL 持久化数据库连接配置
# MySQL 存储用户账号信息和长期对话记录，与 Redis 配合形成冷热数据分层
MYSQL_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),            # MySQL 服务器地址（本机）
    "port": int(os.getenv("MYSQL_PORT", "3306")),            # MySQL 端口（默认 3306）
    "user": os.getenv("MYSQL_USER", "root"),                 # 数据库用户名
    "password": os.getenv("MYSQL_PASSWORD", "123456"),       # 数据库密码（需在 .env 中修改）
    "database": os.getenv("MYSQL_DATABASE", "rag_character_chat"),  # 数据库名
    "charset": "utf8mb4"                                     # 字符集（支持 emoji 和完整 Unicode）
}


# ====================== RAG 参数 ======================
# RAG_CONFIG: 检索增强生成流程的参数配置
# 控制文本分块、向量检索和重排序的行为
RAG_CONFIG = {
    "chunk_size": 512,                                       # 文本分块大小（字符数）
    "chunk_overlap": 50,                                     # 相邻 chunk 的重叠字符数（避免语义断裂）
    "top_k": 10,                                             # Milvus 初始召回数量（粗排阶段）
    "rerank_top_k": 3                                        # Rerank 后保留数量（最终送入 LLM）
}


# ====================== Prompt 控制 ======================
# PROMPT_CONFIG: 控制发送给 LLM 的上下文字数上限
PROMPT_CONFIG = {
    "max_context_length": 2000                                # 最大上下文长度（防止 Prompt 超长截断）
}
