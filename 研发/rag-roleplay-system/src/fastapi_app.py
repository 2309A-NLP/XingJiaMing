# -*- coding: utf-8 -*-
"""
RAG 角色扮演对话系统 — FastAPI 应用主入口 (v2.0 生产版)

┌──────────────────────────────────────────────────────────────────────┐
│ 本文件是整个系统的 HTTP 入口，负责：                                  │
│ 1. API 路由注册（登录、注册、聊天、角色管理等 12 个接口）             │
│ 2. RAG 管线编排（检索 → 判断相关性 → 构建Prompt → LLM → 保存）      │
│ 3. 全局限流（slowapi，防止 DoS 攻击）                                │
│ 4. SSE 流式聊天（逐 token 返回，实现打字机效果）                     │
│ 5. 全局异常捕获 + 请求日志                                           │
│ 6. 注册并挂载静态文件服务（前端 SPA）                                │
├──────────────────────────────────────────────────────────────────────┤
│ 技术栈: FastAPI + Uvicorn + SlowAPI + Jinja2 + Pydantic             │
│ 启动命令: uvicorn src.fastapi_app:app --host 0.0.0.0 --port 8000    │
└──────────────────────────────────────────────────────────────────────┘
"""

# ============================================================================
# 标准库导入 — Python 内置模块，无需额外安装
# ============================================================================
import os  # 文件路径操作（获取 BASE_DIR、拼接静态文件路径等）
import sys  # 系统路径操作（将项目根目录加入 Python 模块搜索路径）
import json  # JSON 序列化（SSE 数据格式、请求/响应序列化）
import time  # 时间函数（计算请求耗时、重试退避等待）
import asyncio  # 异步编程（async/await 支持，StreamingResponse 异步生成器）
import traceback  # 异常栈追踪（未捕获异常的详细日志）
from datetime import datetime  # 时间戳（当前用于 JWT 签发时间，此处保留供后续使用）
from typing import Optional, Dict, Any  # 类型提示（用于函数签名，增强代码可读性）

# ============================================================================
# 第三方框架导入 — FastAPI 生态核心依赖
# ============================================================================
from fastapi import FastAPI, HTTPException, Request, Response, Depends
# FastAPI: Web 框架核心类
# HTTPException: HTTP 异常（用于 404、401 等标准错误响应）
# Request: 请求对象（获取请求方法、路径、IP 等）
# Response: 响应对象（用于自定义响应）
# Depends: 依赖注入（用于 JWT 认证、获取当前用户）

from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
# HTMLResponse: 返回 HTML 页面（首页渲染）
# JSONResponse: 返回 JSON 数据（API 响应）
# StreamingResponse: 流式响应（SSE 聊天，逐 token 返回）

from fastapi.staticfiles import StaticFiles
# 静态文件服务（挂载 CSS/JS/图片等前端资源）

from fastapi.templating import Jinja2Templates
# Jinja2 模板引擎（服务端渲染 HTML）

from fastapi.middleware.cors import CORSMiddleware
# CORS 中间件（处理跨域请求，允许前端从不同域名访问 API）

from pydantic import BaseModel
# Pydantic 数据模型（请求体验证，自动生成 API 文档）

from slowapi import Limiter, _rate_limit_exceeded_handler
# slowapi: 全局限流库
# Limiter: 限流器（配置请求频率上限）
# _rate_limit_exceeded_handler: 限流超限时的默认错误处理

from slowapi.util import get_remote_address
# 获取客户端 IP（用作限流的 key，按 IP 限制请求频率）

from slowapi.errors import RateLimitExceeded
# 限流异常类（触发限流时抛出，注册到 FastAPI 异常处理器）

# ============================================================================
# 项目内部模块导入
# ============================================================================

# ★ 将项目根目录加入 Python 路径，确保相对导入正常工作
# 因为某些启动方式（如直接 python fastapi_app.py）可能导致导入路径错误
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 配置模块 — 读取 .env 文件，提供所有全局配置
from src.config.settings import BASE_DIR, LOG_DIR, LLM_CONFIG, REDIS_CONFIG, MODEL_PATH

# 数据库操作模块
from src.db.mysql import (
    register_user,        # 注册新用户（bcrypt 哈希密码）
    authenticate_user,    # 用户认证（验证密码，返回用户信息）
    get_user_by_id,       # 根据用户 ID 查询用户名
    get_all_characters,   # 获取所有角色列表
    get_character_info,   # 获取单个角色详细信息
    save_chat_message,    # 保存聊天记录到 MySQL（持久存储）
    update_user_role      # 更新用户的当前角色
)

# Redis 缓存操作模块
from src.db.redis import save_message, get_history, clear_history, get_redis_client
# save_message:   保存单条聊天记录到 Redis（短期记忆）
# get_history:    获取对话历史（用于构建 Prompt 上下文）
# clear_history:  清空对话历史（用户点击"清空记录"时调用）
# get_redis_client:获取 Redis 连接实例

# RAG 核心模块
from src.rag.embedding import embed_query, embed_texts
# embed_query:    单条文本嵌入（用户查询 → 1024维向量）
# embed_texts:    批量文本嵌入（知识库文档 → 一批向量）

from src.rag.retrieval import search_vector, milvus_available as pymilvus_available, collections
# search_vector:  在 Milvus 中搜索相似向量（核心检索功能）
# pymilvus_available: Milvus 是否可用（启动时检测，不可用则降级）
# collections:    当前 Milvus 中的所有集合列表

from src.rag.chunking import chunk_text
# chunk_text:     文本分块（将长文档分割成固定长度的文本块）

from src.rag.rerank import rerank
# rerank:         对检索结果进行语义重排序（BGE-Reranker 精排）

# 认证工具模块
from src.utils.auth import create_access_token, get_current_user, get_optional_user
# create_access_token: 生成 JWT Token（用户登录成功后调用）
# get_current_user:    强制认证依赖（请求必须携带有效 JWT，否则 401）
# get_optional_user:   可选认证依赖（允许匿名请求，有 token 就解析）

# 日志工具模块
from src.utils.logger import get_logger, log_request
# get_logger:   获取统一配置的 logger（自动写入文件 + 控制台）
# log_request:  记录 API 请求日志（方法、路径、状态码、耗时）

# 初始化本模块的日志记录器
# 所有模块通过 get_logger(__name__) 获取 logger，实现统一日志格式
logger = get_logger(__name__)


# ============================================================================
# 角色映射表
# 将前端友好的字符串标识（role_id）映射到数据库中的数字主键（character_id）
# 例如: 前端传 roleId="lawyer"，后端转为 character_id=1，再去 MySQL 查角色信息
# ============================================================================
role_map = {'lawyer': 1, 'doctor': 3, 'psych': 2}
# 作用:
#   "lawyer" → 1  → characters 表中 id=1 的"刑事律师（林律）"
#   "doctor" → 3  → characters 表中 id=3 的"医学专家（刘医学）"
#   "psych"  → 2  → characters 表中 id=2 的"心理咨询师（张心理）"

# 有效角色集合（用于快速校验角色是否存在）
VALID_ROLES = set(role_map.keys())  # {"lawyer", "doctor", "psych"}


# ============================================================================
# 全局限流器
# 基于客户端 IP 进行请求频率限制，默认每分钟最多 200 次请求
# 特定接口（如登录、注册、短信）有更严格的独立限流
# ============================================================================
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


# ============================================================================
# FastAPI 应用初始化
# ============================================================================
app = FastAPI(
    title="RAG 角色扮演对话系统",  # API 文档标题（可在 /api/docs 查看）
    version="2.0",                # 应用版本号
    docs_url="/api/docs",         # Swagger 文档路径（访问 /api/docs 查看 API 文档）
    redoc_url=None                # 禁用 ReDoc 文档（保持简洁）
)

# 将限流器绑定到应用实例
# slowapi 通过 app.state.limiter 访问限流配置
app.state.limiter = limiter

# 注册限流超限的异常处理器
# 当请求频率超过限制时，自动返回 429 Too Many Requests
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ============================================================================
# CORS 中间件配置
# 跨域资源共享（Cross-Origin Resource Sharing）
# 作用: 允许前端页面从不同域名/端口访问后端的 API
# 安全原则: 只允许已知的域名，不设置 allow_origins=["*"]
# ============================================================================
app.add_middleware(
    CORSMiddleware,
    # 允许跨域访问的来源域名列表
    allow_origins=[
        "http://localhost:3000",     # 本地开发前端（Vite 默认端口）
        "http://127.0.0.1:8000",     # 本机 FastAPI 服务
        "http://127.0.0.1",          # 本机 HTTP
        "http://120.26.32.90",       # 生产服务器域名
    ],
    allow_credentials=True,   # 允许跨域携带 Cookie
    allow_methods=["GET", "POST"],  # 只允许 GET 和 POST 方法
    allow_headers=["Authorization", "Content-Type"],  # 只允许必要的请求头
)


# ============================================================================
# HTTP 请求日志中间件
# 每个请求都会经过此中间件，记录请求方法、路径、状态码、耗时
# 同时作为全局异常兜底：未捕获的异常在此处统一处理，返回 500
# ============================================================================
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """
    请求日志中间件 — 记录每一次 API 调用的详细信息

    流程:
    1. 记录请求开始时间 (time.monotonic() 适合测量耗时)
    2. 执行实际的路由处理 (call_next)
    3. 如果路由处理抛出异常，在此捕获，记录错误日志 + 返回 500
    4. 计算请求耗时 → 写入结构化日志
    """
    # Step 1: 记录开始时间
    # 使用 time.monotonic() 而非 time.time()，因为 monotonic 不会受系统时间调整影响
    start = time.monotonic()

    try:
        # Step 2: 执行实际的路由处理函数
        # call_next(request) 会调用 FastAPI 路由匹配 → 执行视图函数 → 返回响应
        response = await call_next(request)

    except Exception as exc:
        # Step 3a: 未捕获异常处理（兜底）
        # 任何路由中没有被 try/except 捕获的异常都会到达这里
        # 记录完整异常栈到日志（方便调试），但只向客户端返回通用错误信息
        logger.error(
            f"Unhandled exception: {request.method} {request.url.path}\n"
            f"{traceback.format_exc()}"
        )
        # 返回 500 错误，不暴露内部错误详情（安全考虑）
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "服务器内部错误"}
        )

    # Step 4: 计算请求耗时（毫秒）
    duration_ms = (time.monotonic() - start) * 1000

    # 获取当前用户 ID（如果已认证）
    # request.state 是 FastAPI 的请求状态存储，可在路由/中间件间共享数据
    # 未认证时为 "-"
    user_id = getattr(request.state, "user_id", "-")

    # 写入结构化请求日志
    # 格式: "REQUEST GET /api/roles -> 200 (28ms) [user=1003]"
    log_request(request.method, request.url.path, response.status_code, duration_ms, str(user_id))

    return response


# ============================================================================
# 静态文件 & 模板服务
# 1. 挂载 /static 路径到 static 目录（提供 CSS/JS/图片等前端资源）
# 2. 配置 Jinja2 模板目录（用于服务端渲染 HTML）
# ============================================================================
# 将 static 目录挂载到 /static 路径
# os.path.join(BASE_DIR, "static") → "/root/rag-project/src/static"
# 访问 http://localhost:8000/static/xxx.js 即可获取静态文件
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# 配置 Jinja2 模板引擎，模板文件位于 src/templates/ 目录下
# 模板文件: indexs.html（前端 SPA 单页应用）
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# ============================================================================
# Pydantic 请求模型
# 用于自动验证请求体格式并生成 API 文档
# ============================================================================

class RegisterRequest(BaseModel):
    """注册请求体模型 — 自动校验和文档生成"""
    phone: str       # 手机号（11 位数字，前端已做格式校验）
    password: str    # 密码（不少于 6 位）
    code: str        # 短信验证码（保留字段，前端兼容）
    name: str = ""   # 用户真实姓名（可选，为空时使用手机号作为用户名）


class LoginRequest(BaseModel):
    """登录请求体模型"""
    phone: str       # 手机号
    password: str    # 密码


class ChatRequest(BaseModel):
    """聊天请求体模型 — 非流式 / SSE 流式共用"""
    user_id: int     # 用户 ID（从 JWT 或请求体获取）
    role_id: str     # 角色标识（"lawyer" | "doctor" | "psych"）
    message: str     # 用户发送的消息内容


# ============================================================================
# 辅助函数（非路由，供内部调用）
# ============================================================================

def _llm_chat(prompt: str, question: str, max_retries: int = 2) -> str:
    """
    调用大语言模型（LLM）生成回答，带指数退避重试机制

    参数:
        prompt:     系统提示词（System Prompt，包含角色人设 + 知识库内容）
        question:   用户当前的问题
        max_retries: 最大重试次数，默认 2 次（最多尝试 3 次）

    返回:
        str: LLM 生成的回答文本，或错误提示信息

    重试策略:
        第 1 次失败 → 等待 1s (2^0) 后重试
        第 2 次失败 → 等待 2s (2^1) 后重试
        第 3 次失败 → 返回"服务暂时不可用"

    设计说明:
        - 使用 OpenAI SDK 调用 DeepSeek API（兼容 OpenAI 接口格式）
        - 每次调用都创建新的 OpenAI 客户端实例（避免连接复用导致的问题）
        - 温度设为 0.3（低温度 → 高确定性 → 减少幻觉）
    """
    # 动态导入 OpenAI，避免模块加载时依赖未安装的库
    # 如果项目中用不到 LLM 功能（如仅测试检索），不会因缺少 openai 库而崩溃
    from openai import OpenAI

    # 检查 API Key 是否已配置
    # 如果没有 API Key，直接返回提示信息，不尝试调用
    if not LLM_CONFIG['api_key']:
        return "抱歉，系统未配置大模型API密钥。"

    # 创建 OpenAI 客户端，指向 DeepSeek API 地址
    # base_url 指向 https://api.deepseek.com/v1
    client = OpenAI(api_key=LLM_CONFIG['api_key'], base_url=LLM_CONFIG['api_url'])

    # 构建消息列表
    # System: 设定角色人设 + 知识库内容（双模式 Prompt）
    # User: 用户当前问题
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": question}
    ]

    # 重试循环：max_retries 次重试 + 1 次初次尝试
    # 例如 max_retries=2 → 最多请求 3 次
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            # 调用 DeepSeek API（非流式接口）
            response = client.chat.completions.create(
                model=LLM_CONFIG["model"],           # "deepseek-v4-flash"
                messages=messages,                    # 消息列表
                temperature=0.3,                      # 低温度保证事实性
                max_tokens=1024,                      # 最大生成长度
                timeout=LLM_CONFIG.get("timeout", 90) # 超时时间（默认 90s）
            )
            # 调用成功，记录日志并返回生成的文本内容
            logger.info(f"LLM 调用成功 (attempt={attempt+1})")
            return response.choices[0].message.content

        except Exception as e:
            # 调用失败，记录告警日志
            last_error = e
            logger.warning(f"LLM 调用失败 (attempt={attempt+1}/{max_retries+1}): {e}")
            # 如果不是最后一次尝试，等待指数退避后重试
            # 退避时间: 2^0=1s, 2^1=2s
            if attempt < max_retries:
                time.sleep(2 ** attempt)

    # 所有重试都失败，记录错误日志，返回用户友好的提示
    logger.error(f"LLM 调用最终失败: {last_error}")
    return "抱歉，AI 服务暂时不可用，请稍后再试。"


async def _llm_chat_stream(prompt: str, question: str):
    """
    SSE 流式调用 LLM — 异步生成器，逐 chunk 产出 SSE 格式数据

    原理:
        调用 DeepSeek API 的流式接口 (stream=True)，
        API 会逐 token 返回生成的内容。
        本函数将每个 token 包装为 SSE 格式 (data: {...}\n\n) 并 yield。

    使用场景:
        POST /api/chat/stream 接口，StreamingResponse 消费此生成器

    SSE 数据格式:
        data: {"content": "你"}
        data: {"content": "好"}
        data: {"done": true}
    """
    # 动态导入 OpenAI SDK
    from openai import OpenAI

    # 检查 API Key 是否配置
    if not LLM_CONFIG['api_key']:
        yield f"data: {json.dumps({'error': 'API key 未配置'})}\n\n"
        return

    # 创建 OpenAI 客户端
    client = OpenAI(api_key=LLM_CONFIG['api_key'], base_url=LLM_CONFIG['api_url'])

    # 构建消息列表（同非流式接口）
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": question}
    ]

    try:
        # 调用流式接口
        # stream=True 是关键参数，使 API 以 Server-Sent Events 形式返回
        stream = client.chat.completions.create(
            model=LLM_CONFIG["model"],
            messages=messages,
            temperature=0.3,
            max_tokens=1024,
            stream=True,                          # ★ 流式输出
            timeout=LLM_CONFIG.get("timeout", 90)
        )

        # 遍历流式响应中的每个 chunk
        # 每个 chunk 包含一个 delta（增量内容）
        for chunk in stream:
            # 检查 chunk 中是否有有效的内容
            # 某些 chunk 可能只包含 role 信息（首条）或为空
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                # 以 SSE 格式 yield 当前 token
                yield f"data: {json.dumps({'content': content})}\n\n"

        # 流式输出结束，发送结束标记
        yield f"data: {json.dumps({'done': True})}\n\n"

    except Exception as e:
        # 流式调用失败，记录日志并返回错误信息
        logger.error(f"SSE 流式调用失败: {e}")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


def _build_chat_prompt(
    role_name: str,
    description: str,
    role_prompt: str,
    chat_history: str,
    knowledge_text: str,
    user_name: str = "用户",
    has_knowledge: bool = False
) -> str:
    """
    构建聊天 System Prompt — 双模式策略（★ 核心设计）

    根据是否有相关的知识库内容，使用不同的 Prompt 模板：

    模式 1 — 知识库增强模式 (has_knowledge=True):
        将检索到的知识库内容注入 Prompt，要求 LLM 优先基于知识库回答
        适用于专业问题（如"盗窃罪的量刑标准是什么？"）

    模式 2 — 自由对话模式 (has_knowledge=False):
        不注入知识库内容，让 LLM 以角色身份自由对话
        适用于非专业问题（如"你好"、"今天心情不好"）

    参数:
        role_name:      角色名字（如 "林律"）
        description:    角色描述（如 "专注刑事辩护10年+"）
        role_prompt:    角色指令（如 "你是一位专业的刑事律师..."）
        chat_history:   最近几轮的对话历史文本
        knowledge_text: 检索到的知识库内容
        user_name:      当前用户的名字
        has_knowledge:  是否有相关的知识库内容

    返回:
        str: 完整的 System Prompt
    """
    # ★ 双模式决策: 如果 has_knowledge=True 且 knowledge_text 非空 → 知识库增强模式
    # 否则 → 自由对话模式
    if has_knowledge and knowledge_text:
        # ===== 模式 1: 知识库增强模式 =====
        # 特点: 提供【参考知识库内容】区块，引导 LLM 优先使用知识库回答
        # 同时允许 LLM 在知识库不足时结合自身知识（不强制约束死知识库）
        return f"""你现在是{role_name}，{description}。你正在和{user_name}对话。

【角色指令】
{role_prompt}

【对话历史】
{chat_history if chat_history else "暂无历史"}

【参考知识库内容】
{knowledge_text}

【回答要求】
1. 如果用户的问题涉及专业知识，请优先参考【参考知识库内容】中的信息来回答
2. 如果知识库中有相关信息，请基于这些信息回答
3. 如果知识库中没有直接相关的信息，你可以结合自己的知识来回答
4. 对于非专业问题（如问候、个人信息等），正常回答即可
5. 保持{role_name}的专业语气
6. 回答简洁精准，控制在300字以内"""
    else:
        # ===== 模式 2: 自由对话模式 =====
        # 特点: 没有知识库约束，让 LLM 完全以角色身份自由发挥
        # 适用于问候、闲聊、个人信息询问等场景
        return f"""你现在是{role_name}，{description}。你正在和{user_name}对话。

【角色指令】
{role_prompt}

【对话历史】
{chat_history if chat_history else "暂无历史"}

【回答要求】
1. 请用{role_name}的身份自然地与{user_name}对话
2. 保持{role_name}的专业语气
3. 回答简洁精准，控制在300字以内"""


async def _retrieve_knowledge(question: str, knowledge_base: str) -> tuple:
    """
    RAG 知识检索核心函数 — 向量检索 + 重排序 + 相关性判断

    这是 RAG 管线中最关键的一步，负责从向量知识库中找到与用户问题最相关的内容。

    流程:
    1. 检查 Milvus 是否可用
    2. 确定要搜索的集合名（如 "law_rag"）
    3. 将用户问题转为 1024 维向量 (BGE-M3)
    4. 在 Milvus 中搜索最相似的 TOP-5 文档
    5. 对结果进行语义重排序 (BGE-Reranker)
    6. 判断检索结果是否与问题相关（基于向量距离阈值）
    7. 返回 (知识文本, 是否相关)

    返回:
        tuple: (knowledge_text, is_relevant)
            - knowledge_text: 格式化后的知识文本（用 "---" 分隔多个文档）
            - is_relevant: 知识是否与问题相关（用于触发双模式 Prompt）
    """
    # 检查条件:
    # 1. pymilvus_available: Milvus 服务是否可用（模块启动时检测）
    # 2. knowledge_base: 角色是否配置了知识库（如 "law"）
    if not pymilvus_available or not knowledge_base:
        return "", False

    # 构造 Milvus 集合名: 规则为 "{知识库名}_rag"
    # 例如: law → law_rag, medical → medical_rag, psychology → psychology_rag
    collection_name = f"{knowledge_base}_rag"

    # 检查集合是否存在于 Milvus 中
    # collections 列表在 retrieval.py 模块启动时通过 client.list_collections() 获取
    if collection_name not in collections:
        return "", False

    try:
        # Step 1: 将用户问题转为 1024 维向量
        # embed_query() 内部自动加载 BGE-M3 模型并执行推理
        vec = embed_query(question)

        # Step 2: 在 Milvus 中搜索最相似的 TOP-5 文档
        # L2 距离度量（欧氏距离），距离越小表示越相似
        search_res = search_vector(vec, collection_name, top_k=5)

        # 检查搜索结果是否有效
        if search_res and search_res[0]:
            # Step 3: 获取最相似文档的 L2 距离（用于相关性判断）
            # 距离越小 → 越相似
            top_distance = search_res[0][0]["distance"]

            # Step 4: 提取所有检索到的文档文本
            docs = [hit["entity"]["text"] for hit in search_res[0]]

            # Step 5: 使用 BGE-Reranker 对结果进行语义重排序
            # 重排序能提升 TOP 结果的相关性，弥补向量检索的精度不足
            docs = rerank(question, docs)

            # Step 6: 取重排序后的 TOP-3，格式化为文本块
            knowledge_text = "\n---\n".join(docs[:3])

            # Step 7: 判断检索结果是否与问题相关
            # 原理: BGE-M3 输出的是 L2 归一化向量（所有向量长度为 1）
            # L2 距离范围: [0, 2]
            #   - 0  → 完全相同
            #   - <1 → 有一定相关性（经验阈值）
            #   - >1 → 相关性较弱或无关
            # 阈值 1.0 是经验值，可根据实际效果调整
            is_relevant = top_distance < 1.0

            return knowledge_text, is_relevant

    except Exception as e:
        # 检索过程中任何异常（Milvus 超时、模型加载失败等）都记录日志并优雅降级
        logger.error(f"检索异常: {e}")

    # 降级返回: 空文本 + 不相关
    return "", False


async def _run_chat_pipeline(user_id: int, role_id: str, question: str) -> dict:
    """
    核心聊天管线 — 组织完整的 RAG + LLM + 存储流程

    这是系统最重要的编排函数，链接了检索、生成、存储三大模块。
    被 POST /api/chat 和 POST /api/chat/send 两个接口调用。

    完整流程:
        角色映射 → 获取角色信息 → 获取用户名 → 获取对话历史
        → RAG 检索 → 构建 Prompt → LLM 生成 → 保存历史 → 返回

    参数:
        user_id:   用户 ID（来自 JWT 或请求体）
        role_id:   角色标识（"lawyer" | "doctor" | "psych"）
        question:  用户消息

    返回:
        dict: {"success": bool, "message": str}
            success=True:  回答文本在 message 中
            success=False: 错误描述在 message 中
    """
    # Step 1: 角色映射 — 将字符串 role_id 转为数字 character_id
    # role_map = {"lawyer": 1, "doctor": 3, "psych": 2}
    character_id = role_map.get(role_id)
    if character_id is None:
        # 如果传入的 role_id 不在映射表中（如 "judge"），返回错误
        return {"success": False, "message": f"无效角色: {role_id}"}

    # Step 2: 从 MySQL 获取角色详细信息
    # get_character_info 内部有降级逻辑，即使 MySQL 不可用也返回默认角色数据
    character = get_character_info(character_id)
    if not character:
        return {"success": False, "message": "角色不存在"}

    # Step 3: 获取用户信息（用于注入用户名到 Prompt，提升对话沉浸感）
    user_info = get_user_by_id(user_id)
    user_name = user_info["username"] if user_info else "用户"

    # Step 4: 提取角色相关配置
    role_name = character["name"]           # 如 "林律"
    role_prompt = character["prompt_template"]  # 角色人设指令
    knowledge_base = character["knowledge_base"]  # 知识库名，如 "law"

    # Step 5: 从 Redis 获取最近几轮的对话历史
    # 格式化的历史文本: "用户：你好\n助手：你好，我是林律..."
    chat_history = get_history(user_id, role_id)

    # Step 6: ★ RAG 检索 — 从专业知识库中查找相关内容
    # 返回: (知识文本, 是否相关)
    knowledge_text, is_relevant = await _retrieve_knowledge(question, knowledge_base)

    # Step 7: ★ 构建 System Prompt — 双模式
    # 根据 is_relevant 决定使用知识库增强模式还是自由对话模式
    prompt = _build_chat_prompt(
        role_name, character["description"],
        role_prompt, chat_history, knowledge_text,
        user_name=user_name, has_knowledge=is_relevant
    )

    # Step 8: 调用 LLM 生成回答（带重试机制）
    answer = _llm_chat(prompt, question)

    # Step 9: 保存聊天记录
    # Redis 短期记忆（用于对话上下文，5 分钟过期）
    save_message(user_id, role_id, "user", question)
    save_message(user_id, role_id, "assistant", answer)
    # MySQL 持久存储（用于历史查询和数据分析）
    save_chat_message(user_id, character_id, "user", question)
    save_chat_message(user_id, character_id, "assistant", answer)

    # Step 10: 返回成功响应
    return {"success": True, "message": answer}


# ============================================================================
# API 路由 — 首页
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    首页 — 返回前端 SPA 页面
    使用 Jinja2 渲染 indexs.html 模板
    """
    return templates.TemplateResponse("indexs.html", {"request": request})


# ============================================================================
# API 路由 — 健康检查
# ============================================================================

@app.get("/api/health")
async def health_check():
    """
    健康检查端点 — 检测所有依赖服务的状态

    返回:
        {
            "status": "healthy" | "degraded",
            "services": {
                "mysql": "ok" | "degraded" | "down: xxx",
                "redis": "ok" | "down: xxx",
                "milvus": "ok" | "unavailable",
                "llm_api": "configured" | "missing"
            }
        }

    设计说明:
        - 不要求所有服务都正常才算健康（如 Milvus 不可用可降级）
        - 只要核心功能可用就返回 healthy
        - 服务级异常会导致 status 降级为 degraded
    """
    status = {
        "status": "healthy",   # 默认健康，发现异常时降级
        "version": "2.0",      # 当前版本号
        "services": {}         # 各服务状态详情
    }

    # 检测 MySQL: 尝试查询角色表
    try:
        roles = get_all_characters()
        status["services"]["mysql"] = "ok" if roles else "degraded"
    except Exception as e:
        status["services"]["mysql"] = f"down: {str(e)[:50]}"
        status["status"] = "degraded"  # MySQL 不可用 → 降级

    # 检测 Redis: 发送 PING 命令
    try:
        r = get_redis_client()
        r.ping()
        status["services"]["redis"] = "ok"
    except Exception as e:
        status["services"]["redis"] = f"down: {str(e)[:50]}"
        status["status"] = "degraded"  # Redis 不可用 → 降级

    # 检测 Milvus: 读取模块启动时的连接状态
    # pymilvus_available 在 retrieval.py 模块导入时设置
    status["services"]["milvus"] = "ok" if pymilvus_available else "unavailable"

    # 检测 LLM API: 检查是否配置了 API Key
    status["services"]["llm_api"] = "configured" if LLM_CONFIG.get('api_key') else "missing"

    return status


# ============================================================================
# API 路由 — 用户注册
# ============================================================================

@app.post("/api/register")
@limiter.limit("10/minute")  # ★ 限流: 每分钟最多注册 10 次
async def register(request: Request, body: RegisterRequest):
    """
    用户注册 — 创建新账户

    流程:
        1. 校验请求体（Pydantic 自动完成）
        2. 调用 register_user() 在 MySQL 中创建用户
        3. 如果手机号已存在，返回错误
        4. 成功返回 success: true

    安全:
        - 10 次/分钟限流（防止批量注册）
        - bcrypt 哈希密码（register_user 内部完成）
    """
    try:
        # 注册用户: 参数为 (手机号, 密码, 姓名)
        # 返回 True 表示成功，False 表示手机号已存在
        result = register_user(body.phone, body.password, body.name)

        # 根据结果返回对应的提示信息
        return {"success": True, "message": "注册成功"} if result else \
               {"success": False, "message": "该手机号已注册"}

    except Exception as e:
        # 记录异常日志，返回错误信息
        logger.error(f"注册失败: {e}")
        return {"success": False, "message": str(e)}


# ============================================================================
# API 路由 — 用户登录
# ============================================================================

@app.post("/api/login")
@limiter.limit("20/minute")  # ★ 限流: 每分钟最多登录 20 次
async def login(request: Request, body: LoginRequest):
    """
    用户登录 — 验证密码并签发 JWT Token

    流程:
        1. 校验请求体（手机号 + 密码）
        2. authenticate_user() 验证密码（bcrypt 校验）
        3. 成功 → 签发 JWT Token（72 小时过期）
        4. 返回 Token + 用户信息

    返回 Token 信息:
        - token: JWT 字符串
        - token_type: "Bearer"（标准 HTTP 认证头格式）
        - expires_in: 259200 秒（72 小时）

    安全:
        - 20 次/分钟限流（防止暴力破解）
        - 密码错误返回统一提示（不泄露是手机号不存在还是密码错）
        - 内部异常不对外暴露（返回"系统繁忙"）
    """
    try:
        # 认证用户: 验证手机号和密码
        # 返回 dict: 成功 → {"id": 1, "username": "张三"}
        #          失败 → {"error": "手机号未注册"} 或 {"error": "密码错误"}
        result = authenticate_user(body.phone, body.password)

        # 检查认证结果: 如果包含 "id" 字段说明认证成功
        if result and "id" in result:
            # ★ 签发 JWT Token: 包含 user_id, phone, username
            # 过期时间 72 小时 (259200 秒)
            token = create_access_token(result["id"], body.phone, result["username"])

            # 返回完整的登录成功响应
            return {
                "success": True,
                "message": "登录成功",
                "user": {"id": result["id"], "username": result["username"]},  # 用户信息
                "token": token,                   # JWT 字符串
                "token_type": "Bearer",           # 认证头格式
                "expires_in": 259200              # 过期时间（秒）
            }

        # 认证失败: 提取错误信息，优先使用后端返回的具体错误
        error_msg = result.get("error", "手机号或密码错误") if result else "手机号或密码错误"
        return {"success": False, "message": error_msg}

    except Exception as e:
        # 记录异常日志，不对外暴露内部错误
        logger.error(f"登录失败: {e}")
        return {"success": False, "message": "系统繁忙，请稍后重试"}


# ============================================================================
# API 路由 — 角色管理
# ============================================================================

@app.get("/api/roles")
async def get_roles_api():
    """
    获取所有角色列表 — 用于角色选择页

    返回:
        {
            "success": true,
            "data": [
                {"id": 1, "name": "林律", "role_type": "lawyer", "description": "..."},
                {"id": 2, "name": "张心理", "role_type": "psych", "description": "..."},
                {"id": 3, "name": "刘医学", "role_type": "doctor", "description": "..."}
            ]
        }

    降级策略:
        MySQL 不可用时返回硬编码的默认角色列表
    """
    try:
        roles = get_all_characters()
        return {"success": True, "data": roles}
    except Exception as e:
        logger.error(f"获取角色列表失败: {e}")
        return {"success": False, "message": str(e)}


@app.get("/api/character/{role_id}")
async def get_character(role_id: str):
    """
    获取指定角色的详细信息

    参数:
        role_id: 角色标识（"lawyer" | "doctor" | "psych"）

    返回:
        成功: {success: true, data: {id, name, description, prompt, knowledge_base}}
        失败: {success: false, message: "..."}
        角色不存在: HTTP 404

    设计说明:
        - 前端进入聊天页时调用此接口获取角色 Prompt 和知识库信息
        - 如果 role_id 不在 VALID_ROLES 中，返回 404
    """
    # 校验角色是否存在
    if role_id not in VALID_ROLES:
        raise HTTPException(status_code=404, detail=f"角色不存在: {role_id}")

    try:
        # 将 role_id 转为 character_id
        character_id = role_map[role_id]
        # 从 MySQL 获取角色详情（有降级逻辑）
        character = get_character_info(character_id)

        if character:
            # 返回角色信息（只返回前端需要的字段）
            return {"success": True, "data": {
                "id": character["id"],
                "name": character["name"],
                "description": character["description"],
                "prompt": character["prompt_template"],     # 人设 Prompt
                "knowledge_base": character["knowledge_base"]  # 关联知识库
            }}

        return {"success": False, "message": "角色不存在"}

    except Exception as e:
        logger.error(f"获取角色信息失败: {e}")
        return {"success": False, "message": str(e)}


@app.post("/api/user/role")
async def update_role(role_id: str, current_user: Dict = Depends(get_current_user)):
    """
    切换用户当前角色

    安全:
        - 需要 JWT 认证（Depends(get_current_user)）
        - 只能修改自己的角色（user_id 从 JWT 提取，不接受参数传入）

    参数:
        role_id: 目标角色标识（"lawyer" | "doctor" | "psych"）
        current_user: 当前登录用户信息（由 JWT 注入）
    """
    try:
        # ★ 从 JWT 中提取用户 ID，而非从请求参数中获取（防止越权）
        user_id = current_user["user_id"]
        # 更新用户在 MySQL 中的角色记录
        result = update_user_role(user_id, role_id)

        return {"success": True, "message": "角色切换成功"} if result else \
               {"success": False, "message": "角色切换失败"}

    except Exception as e:
        logger.error(f"角色切换失败: {e}")
        return {"success": False, "message": str(e)}


# ============================================================================
# API 路由 — 聊天（非流式）
# ============================================================================

@app.post("/api/chat")
async def chat(body: ChatRequest):
    """
    核心聊天接口（非流式）— 完整 RAG 管线

    请求体:
        {"user_id": 1003, "role_id": "lawyer", "message": "盗窃罪判几年？"}

    返回:
        {"success": true, "message": "根据刑法规定..."}

    处理流程:
        _run_chat_pipeline() 内部完成:
        检索 → 相关性判断 → 构建Prompt → LLM → 保存历史 → 返回
    """
    return await _run_chat_pipeline(body.user_id, body.role_id, body.message)


# ============================================================================
# API 路由 — 聊天（SSE 流式）
# ============================================================================

@app.post("/api/chat/stream")
async def chat_stream(body: ChatRequest):
    """
    SSE 流式聊天接口 — 逐 token 返回（★ 演示高亮功能）

    不同于非流式接口在 LLM 完成全部生成后才返回，
    流式接口每生成一个 token 就立即推送给前端，
    实现"打字机效果"，显著提升用户体验。

    请求体:
        {"user_id": 1003, "role_id": "lawyer", "message": "你好"}

    响应:
        Content-Type: text/event-stream
        data: {"content": "你"}
        data: {"content": "好"}
        data: {"content": "，"}
        data: {"content": "我"}
        data: {"done": true}

    技术实现:
        1. 角色校验 + 信息获取（同非流式）
        2. RAG 检索 + 构建 Prompt（同非流式）
        3. 使用 StreamingResponse 包装异步生成器
        4. 异步生成器消费 LLM 的流式输出
        5. 生成完毕保存聊天记录
    """
    # Step 1: 校验角色是否存在
    character_id = role_map.get(body.role_id)
    if character_id is None:
        return JSONResponse(
            {"success": False, "message": f"无效角色: {body.role_id}"},
            status_code=400
        )

    # Step 2: 获取角色详细信息
    character = get_character_info(character_id)
    if not character:
        return JSONResponse(
            {"success": False, "message": "角色不存在"},
            status_code=404
        )

    # Step 3: 获取用户名（用于 Prompt）
    user_info = get_user_by_id(body.user_id)
    user_name = user_info["username"] if user_info else "用户"

    # Step 4: RAG 检索
    knowledge_text, is_relevant = await _retrieve_knowledge(
        body.message, character["knowledge_base"]
    )

    # Step 5: 获取对话历史
    chat_history = get_history(body.user_id, body.role_id)

    # Step 6: 构建 System Prompt
    prompt = _build_chat_prompt(
        character["name"], character["description"],
        character["prompt_template"], chat_history, knowledge_text,
        user_name=user_name, has_knowledge=is_relevant
    )

    # Step 7: 定义异步生成器（★ 核心）
    async def generate():
        """
        异步生成器 — 消费 LLM 流式输出并逐 token 推送给前端

        工作原理:
            1. 调用 _stream_chunks() 获得 LLM 的流式 token
            2. 每个 token 包装为 SSE 格式 "data: {...}\n\n"
            3. 收集所有 token 用于最后的完整回答
            4. 流结束后保存聊天记录到 Redis + MySQL
        """
        full_answer = []  # 收集所有 token 用于持久化

        # 逐 token 消费流式输出
        async for chunk_data in _stream_chunks(prompt, body.message):
            # 收集 token 内容
            full_answer.append(chunk_data.get("content", ""))
            # 以 SSE 格式 yield 给 StreamingResponse
            yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"

        # 流式输出结束，拼接完整回答
        final_answer = "".join(full_answer)

        # 保存聊天记录到 Redis（短期记忆）
        save_message(body.user_id, body.role_id, "user", body.message)
        save_message(body.user_id, body.role_id, "assistant", final_answer)
        # 保存聊天记录到 MySQL（持久存储）
        save_chat_message(body.user_id, character_id, "user", body.message)
        save_chat_message(body.user_id, character_id, "assistant", final_answer)

    # 返回 StreamingResponse，content-type 设为 text/event-stream
    # 浏览器收到此响应头后会保持连接打开，持续接收数据
    return StreamingResponse(generate(), media_type="text/event-stream")


async def _stream_chunks(prompt: str, question: str):
    """
    解析 SSE 流式数据的异步生成器

    将 _llm_chat_stream_sync（同步生成器）包装为异步生成器，
    解析 SSE 格式的 "data: {...}" 行为 Python 字典。

    输入:  "data: {"content": "你"}\n\n"
    输出:  {"content": "你"}

    忽略: 格式错误的行（如空行、非 JSON 行）
    """
    # 消费同步生成器中的每个 SSE 数据块
    for chunk_text in _llm_chat_stream_sync(prompt, question):
        try:
            # 去掉 "data: " 前缀和首尾空白，解析 JSON
            # 例如: "data: {"content": "你"}\n\n" → {"content": "你"}
            yield json.loads(chunk_text.replace("data: ", "").strip())
        except json.JSONDecodeError:
            # 忽略无法解析的行（如空行）
            pass


def _llm_chat_stream_sync(prompt: str, question: str):
    """
    LLM 流式调用的同步生成器 — 逐 chunk 产出 SSE 格式数据

    由于 OpenAI SDK 的流式接口是同步的（for chunk in stream），
    但 FastAPI 的 StreamingResponse 接受的生成器可以是同步的，
    因此这里使用同步生成器，再由 _stream_chunks 包装为异步生成器。

    产出格式: "data: {json_string}\n\n"
    """
    from openai import OpenAI
    import json as _json

    # 检查 API Key
    if not LLM_CONFIG['api_key']:
        yield f"data: {_json.dumps({'error': 'API key 未配置'})}\n\n"
        return

    # 创建 OpenAI 客户端
    client = OpenAI(api_key=LLM_CONFIG['api_key'], base_url=LLM_CONFIG['api_url'])

    # 构建消息列表
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": question}
    ]

    try:
        # 调用 DeepSeek 流式接口
        stream = client.chat.completions.create(
            model=LLM_CONFIG["model"],
            messages=messages,
            temperature=0.3,
            max_tokens=1024,
            stream=True,       # ★ 流式输出
            timeout=90         # 超时 90 秒
        )

        # 遍历流式响应的每个 chunk
        for chunk in stream:
            # 提取当前 token 的内容
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                # 以 SSE 格式产出
                yield f"data: {_json.dumps({'content': content}, ensure_ascii=False)}\n\n"

        # 发送结束标记
        yield f"data: {_json.dumps({'done': True})}\n\n"

    except Exception as e:
        # 异常时记录错误并返回错误信息
        logger.error(f"SSE 流式调用失败: {e}")
        yield f"data: {_json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"


# ============================================================================
# API 路由 — 前端兼容聊天
# ============================================================================

@app.post("/api/chat/send")
async def chat_send(request: Request, current_user: Dict = Depends(get_current_user)):
    """
    前端兼容聊天接口（专为前端 SPA 设计）

    与前端的区别:
        标准接口:  POST /api/chat    → 参数为 user_id, role_id, message
        前端接口:  POST /api/chat/send → 参数为 roleId, message + JWT 认证

    安全:
        ★ 用户 ID 从 JWT Token 中提取（current_user["user_id"]），
          而非从请求体获取，防止身份伪造

    请求体:
        {"roleId": "lawyer", "message": "你好"}
    请求头:
        Authorization: Bearer <token>

    返回:
        成功: {"code": 200, "data": {"reply": "..."}}
        失败: {"code": 500, "message": "..."}
    """
    try:
        # 解析请求体（使用 request.json() 而非 Pydantic 模型，兼容前端字段名）
        body = await request.json()
        # 兼容两种字段名: roleId（前端）/ role_id（后端）
        role_id = body.get('roleId') or body.get('role_id')
        message = body.get('message')

        # 参数校验
        if not role_id or not message:
            return {"code": 400, "message": "缺少必要参数"}

        # ★ 从 JWT 中提取用户 ID（安全：不接受来自请求体的 user_id）
        user_id = current_user["user_id"]

        # 执行 RAG 聊天管线
        result = await _run_chat_pipeline(user_id, role_id, message)

        if result.get('success'):
            return {"code": 200, "data": {"reply": result.get('message', '')}}
        return {"code": 500, "message": result.get('message', '服务器错误')}

    except Exception as e:
        logger.error(f"chat_send 异常: {e}")
        return {"code": 500, "message": "服务器内部错误"}


# ============================================================================
# API 路由 — 清空聊天历史
# ============================================================================

@app.delete("/api/chat/history")
async def delete_chat_history(role_id: str, current_user: Dict = Depends(get_current_user)):
    """
    清空当前用户与指定角色的聊天历史

    安全:
        - 需要 JWT 认证
        - 只清空自己的历史（user_id 来自 JWT）

    参数:
        role_id: 角色标识（"lawyer" | "doctor" | "psych"）
        current_user: 当前用户信息（由 JWT 注入）
    """
    # 校验角色有效性
    if role_id not in VALID_ROLES:
        return {"success": False, "message": f"无效角色: {role_id}"}

    try:
        # 从 JWT 提取用户 ID
        user_id = current_user["user_id"]
        # 将 role_id 转为 character_id
        character_id = role_map[role_id]
        # 调用 Redis 清空函数
        clear_history(user_id, character_id)
        return {"success": True, "message": "聊天记录已清空"}
    except Exception as e:
        logger.error(f"清空历史失败: {e}")
        return {"success": False, "message": "清空失败"}


# ============================================================================
# API 路由 — 短信验证码
# ============================================================================

@app.post("/api/sms/send")
@limiter.limit("3/minute")  # ★ 限流: 每分钟最多发送 3 次（防短信轰炸）
async def send_sms(request: Request, phone: str):
    """
    发送短信验证码

    功能:
        1. 检查 60 秒冷却期（同一手机号不能频繁发送）
        2. 生成 6 位随机验证码
        3. 存入 Redis（300 秒有效）
        4. 设置冷却期（60 秒）

    安全:
        - 3 次/分钟限流
        - 60 秒发送冷却期
        - 验证码 5 分钟有效

    注意:
        当前为演示版本，验证码仅存入 Redis 日志，不实际发送 SMS。
        生产环境可对接阿里云 SMS、腾讯云 SMS 等短信服务。
    """
    try:
        # 获取 Redis 连接
        r = get_redis_client()

        # 检查冷却期: 同一手机号 60 秒内不能重复发送
        cooldown_key = f"sms_cooldown:{phone}"
        if r.exists(cooldown_key):
            ttl = r.ttl(cooldown_key)  # 剩余冷却时间（秒）
            return {"success": False, "message": f"发送太频繁，请{ttl}秒后再试"}

        # 生成 6 位随机验证码
        import random
        code = str(random.randint(100000, 999999))

        # 存入 Redis: 验证码 300 秒有效
        r.setex(f"sms_code:{phone}", 300, code)
        # 设置冷却期: 60 秒内不可重复发送
        r.setex(cooldown_key, 60, "1")

        # 记录日志（生产环境应替换为实际 SMS 发送）
        logger.info(f"验证码已发送至 {phone}")
        return {"success": True, "message": "验证码已发送"}

    except Exception as e:
        logger.error(f"发送验证码失败: {e}")
        return {"success": False, "message": str(e)}


@app.post("/api/sms/verify")
async def verify_sms(phone: str, code: str):
    """
    验证短信验证码

    校验流程:
        1. 从 Redis 获取该手机号存储的验证码
        2. 与用户输入的验证码比对
        3. 匹配 → 删除验证码（一次性使用）→ 返回成功
        4. 不匹配 → 返回失败
    """
    try:
        r = get_redis_client()
        # 从 Redis 获取之前存储的验证码
        stored_code = r.get(f"sms_code:{phone}")

        # 校验验证码
        if stored_code and stored_code == code:
            # 验证成功，删除已使用的验证码（防止重复使用）
            r.delete(f"sms_code:{phone}")
            return {"success": True, "message": "验证成功"}

        # 验证码错误或已过期
        return {"success": False, "message": "验证码错误或已过期"}

    except Exception as e:
        logger.error(f"验证码校验失败: {e}")
        return {"success": False, "message": str(e)}


# ============================================================================
# 应用启动入口
# 仅在直接运行 python fastapi_app.py 时执行
# 使用 uvicorn 启动时（推荐方式）不会执行此块
# ============================================================================
if __name__ == "__main__":
    import uvicorn
    # 生产环境推荐使用命令行启动:
    # uvicorn src.fastapi_app:app --host 0.0.0.0 --port 8000 --workers 2 --log-level info
    uvicorn.run(app, host="0.0.0.0", port=8000)
