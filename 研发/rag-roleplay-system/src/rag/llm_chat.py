# -*- coding: utf-8 -*-  # 指定文件编码为 utf-8
"""
大模型交互模块（LLM Chat）

本模块负责与外部大模型 API 进行交互，是 RAG 系统的响应生成组件。

主要功能：
1. 通用的大模型对话接口（chat_with_llm）
2. 法律领域专用对话接口（chat_with_law）

技术栈：
- OpenAI Python SDK: 用于调用兼容 OpenAI 格式的大模型 API
- DeepSeek API: 默认使用的 LLM 服务（兼容 OpenAI SDK）

架构位置：
用户查询 → Embedding → Milvus 检索 → Rerank 精排 → LLM 生成回复（本模块）

RAG 流程的最后一步：将检索到的知识作为上下文，让 LLM 基于知识生成回答。
"""

import os                              # 系统接口
from openai import OpenAI              # OpenAI SDK（兼容 DeepSeek API）
from src.config.settings import LLM_CONFIG  # LLM 配置（API Key、地址、模型名等）

# 从配置中读取 API 密钥和基础地址
API_KEY = LLM_CONFIG.get("api_key", "")      # DeepSeek API Key
API_URL = LLM_CONFIG.get("api_url", "https://api.deepseek.com")  # API 端点

# 创建 OpenAI 客户端实例
# DeepSeek API 完全兼容 OpenAI SDK 格式
# 只需要修改 base_url 为 DeepSeek 的地址即可无缝切换
client = OpenAI(api_key=API_KEY, base_url=API_URL)


def chat_with_llm(messages, model="deepseek-v4-flash"):
    """
    调用大模型进行通用对话

    支持传入自定义的消息列表，适用于各种对话场景。
    消息格式遵循 OpenAI API 标准：
    - system: 系统提示词，设定 AI 的角色和行为
    - user: 用户消息
    - assistant: AI 的回复（可用于多轮对话历史）

    Args:
        messages: 消息列表，格式为 [
            {"role": "system", "content": "你是一个...的人设"},
            {"role": "user", "content": "用户问题"}
        ]
        model: 模型名称，默认 deepseek-v4-flash

    Returns:
        str: 大模型的回复内容，如果请求失败返回错误描述
    """
    try:
        # 调用大模型 API 的非流式接口
        # stream=False 表示等待完整回复返回（非流式）
        # 流式接口用于前端 SSE（Server-Sent Events），此处未使用
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=False
        )

        # 从响应中提取助手的回复文本
        # choices[0] 是第一个（也是唯一一个）回复候选
        # message.content 是回复的文本内容
        return response.choices[0].message.content

    except Exception as e:
        # 任何 API 调用异常（网络错误、鉴权失败、超时等）
        # 返回错误信息而非抛出异常，避免调用方崩溃
        return f"请求失败：{str(e)}"


def chat_with_law(query: str, law_context: str, history=None):
    """
    法律领域专用对话接口

    为刑事律师角色定制，自动构造包含法律条文上下文的 Prompt。
    采用"知识增强"模式：将检索到的法律条文作为参考信息，让 LLM 基于条文回答。

    Prompt 结构：
    1. system 消息：定义律师人设（语气亲切、专业可靠）
    2. user 消息：包含法律条文 + 历史对话 + 用户当前问题

    Args:
        query: 用户的法律问题
        law_context: 从知识库检索到的相关法律条文（Milvus + Rerank 的输出）
        history: 与用户的对话历史（从 Redis 读取），用于多轮对话上下文

    Returns:
        str: 法律专家风格的回复
    """
    try:
        # 构建历史对话文本（如果有）
        history_text = ""
        if history and history.strip():
            history_text = f"\n之前的对话：\n{history}"

        # 构建用户提示词（Prompt 工程的核心部分）
        # 将法律条文和用户问题组织成清晰的指令格式
        user_prompt = f"""以下是相关的法律条文依据：
---
{law_context}
---

当事人的问题：{query}{history_text}

请根据上述法条，用自然亲切的方式为当事人解答这个问题。"""

        # 构建完整的消息列表
        messages = [
            # system 消息：定义 AI 的角色、身份和说话风格
            # 这是 Prompt 工程的关键——角色设定直接影响回复质量
            {"role": "system", "content": "你是一位经验丰富、专业可靠的刑事律师，名叫林律。你最大的特点是用通俗易懂的语言为当事人解答法律问题。请用自然、亲切的方式回答，就像在和当事人面对面交流一样。"},
            # user 消息：包含法律依据、历史对话和当前问题
            {"role": "user", "content": user_prompt}
        ]

        # 调用通用对话接口
        return chat_with_llm(messages)

    except Exception as e:
        return f"请求失败：{str(e)}"
