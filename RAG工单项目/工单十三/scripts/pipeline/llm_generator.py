"""LLM answer generation utilities."""
from __future__ import annotations

import logging
import os
import time as _time

from openai import OpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_ZH = """你是一个智能文档助手。

你手上有两部分信息：
1. 对话历史：之前和用户的聊天记录
2. 参考资料：从文档中检索到的内容

要求：
1. 优先依据对话历史和参考资料回答，不要编造
2. 找不到答案时明确说明“参考资料中未找到相关信息”
3. 问候和闲聊自然回复
4. 回答尽量简洁清晰，需要对比时使用 Markdown 表格
"""

SYSTEM_PROMPT_EN = """You are an intelligent document assistant.

Use the supplied reference materials when they are relevant.
If the answer is not in the materials, say so honestly.
Be concise and friendly.
"""


class Generator:
    """Generate answers from retrieved contexts with an OpenAI-compatible API."""

    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        resolved_api_key = api_key or os.getenv("MIMO_API_KEY")
        resolved_base_url = base_url or os.getenv("MIMO_BASE_URL")
        self._client = None
        if resolved_api_key:
            self._client = OpenAI(
                api_key=resolved_api_key,
                base_url=resolved_base_url,
                timeout=30.0,
            )
        else:
            logger.warning("MIMO_API_KEY 未配置，完整 LLM 生成链路将不可用")

        self._model = model or os.getenv("MIMO_MODEL", "deepseek-chat")
        self._max_context_chars = int(os.getenv("MAX_CONTEXT_CHARS", "3200"))
        self._max_tokens = int(os.getenv("MAX_COMPLETION_TOKENS", "480"))

    def _require_client(self) -> None:
        if self._client is None:
            raise RuntimeError("LLM API 未配置，请在 .env 中设置 MIMO_API_KEY")

    def _build_context(self, contexts: list) -> str:
        parts = []
        total_chars = 0
        for i, ctx in enumerate(contexts, start=1):
            metadata = getattr(ctx, "metadata", {}) if hasattr(ctx, "metadata") else ctx
            title = metadata.get("section_title", "")
            source = metadata.get("source_file", "")
            content = ctx.content if hasattr(ctx, "content") else ctx.get("content", "")
            source_label = source.replace("_refined.md", "").replace(".md", "") if source else ""
            header = f"【资料{i}·来源：{source_label}】{title}" if source_label else f"【资料{i}】{title}"
            block = f"{header}\n{content}".strip()
            if parts and total_chars + len(block) > self._max_context_chars:
                break
            if not parts and len(block) > self._max_context_chars:
                block = block[: self._max_context_chars]
            parts.append(block)
            total_chars += len(block)
        return "\n\n".join(parts)

    def _build_messages(self, prompt: str, user_prompt: str, history: list = None) -> list:
        messages = [{"role": "system", "content": prompt}]
        if history:
            for item in history:
                role = item.get("role", "user")
                if role in ("user", "assistant"):
                    messages.append({"role": role, "content": item.get("content", "")})
        messages.append({"role": "user", "content": user_prompt})
        return messages

    def generate(self, query: str, contexts: list, language: str = "zh", history: list = None) -> str:
        self._require_client()
        context_text = self._build_context(contexts)
        prompt = SYSTEM_PROMPT_EN if language == "en" else SYSTEM_PROMPT_ZH
        user_prompt = (
            f"Reference materials:\n{context_text}\n\nQuestion: {query}"
            if language == "en"
            else f"参考资料：\n{context_text}\n\n问题：{query}"
        )

        last_err = None
        for attempt in range(3):
            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=self._build_messages(prompt, user_prompt, history),
                    temperature=0.1,
                    max_tokens=self._max_tokens,
                    timeout=15.0,
                )
                answer = (resp.choices[0].message.content or "").strip()
                logger.info("LLM 回答生成完成: %d 字", len(answer))
                return answer
            except Exception as exc:
                last_err = exc
                if attempt < 2:
                    wait = (attempt + 1) * 0.5
                    logger.warning("LLM 调用失败，第 %d 次重试前等待 %.1fs: %s", attempt + 1, wait, str(exc)[:120])
                    _time.sleep(wait)
        raise last_err

    def generate_stream(self, query: str, contexts: list, language: str = "zh", history: list = None):
        if self._client is None:
            yield "[Error: LLM API 未配置，请在 .env 中设置 MIMO_API_KEY]"
            return

        context_text = self._build_context(contexts)
        prompt = SYSTEM_PROMPT_EN if language == "en" else SYSTEM_PROMPT_ZH
        user_prompt = (
            f"Reference materials:\n{context_text}\n\nQuestion: {query}"
            if language == "en"
            else f"参考资料：\n{context_text}\n\n问题：{query}"
        )
        messages = self._build_messages(prompt, user_prompt, history)

        last_err = None
        for attempt in range(3):
            try:
                stream = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=self._max_tokens,
                    stream=True,
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
                return
            except Exception as exc:
                last_err = exc
                if attempt < 2:
                    wait = float(attempt + 1)
                    logger.warning("LLM 流式调用失败，第 %d 次重试前等待 %.1fs: %s", attempt + 1, wait, str(exc)[:120])
                    _time.sleep(wait)
                else:
                    logger.error("LLM 流式调用最终失败: %s", str(exc))
        yield f"[Error: {last_err}]"
