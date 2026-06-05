"""LLM 生成回答"""
from __future__ import annotations
import logging
import os
import time as _time
from typing import List
from openai import OpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_ZH = """你是一个智能文档助手。

你手上有从多份文档中检索到的参考资料（会附在用户消息中）。每份资料标注了【来源文档】。

【核心规则 - 必须遵守】
1. 只用参考资料里的信息回答，不要添加参考资料中没有的内容
2. 优先使用原文的措辞和表述，不要自己换一种说法
3. 覆盖参考资料中所有与问题相关的要点，不要遗漏
4. 数据必须注明来源或时间段，不要混淆不同年代/期间的数据
5. 不要添加原文没有的定性判断（如"较高""较低"），除非原文明确说了
6. 如果资料里找不到答案，坦诚说"参考资料中未找到相关信息"
7. 闲聊/问候时自然友好回应，不用看资料

【多文档规则】
- 如果用户问的是某家公司的信息，只用该公司的文档回答，不要混入其他公司的数据
- 如果用户问"文档一和文档二的区别"或类似问题，明确说明每份文档分别是什么
- 回答时说明信息来自哪份文档（如"根据《招股说明书1》..."）
- 不同文档可能涉及不同公司，注意区分，不要张冠李戴

【格式要求】
- 涉及多个同类项目、指标、时间点、对比项时，使用 Markdown 表格
- 先用 1-2 句话给出结论，再给表格或详细说明
- 数字保留原始精度，不要凑整
- 不要一开口就说"根据参考资料"
- 没有结构化内容时不要硬塞表格"""

SYSTEM_PROMPT_EN = """You are an intelligent document assistant. Answer in English.

Rules:
- If the question relates to the document, use the reference materials to answer
- If greeting or chatting, respond naturally and friendly
- If no answer found, say so honestly

Style: Concise and warm. Use Markdown tables for comparisons. Keep number precision."""


class Generator:
    """用 LLM 根据检索结果生成回答。"""

    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        self._client = OpenAI(
            api_key=api_key or os.getenv('MIMO_API_KEY'),
            base_url=base_url or os.getenv('MIMO_BASE_URL'),
            timeout=30.0,
        )
        self._model = model or os.getenv('MIMO_MODEL', 'deepseek-chat')

    def _build_context(self, contexts: list) -> str:
        """构建上下文文本，包含来源文档信息"""
        parts = []
        for i, c in enumerate(contexts):
            title = getattr(c, 'metadata', {}).get('section_title', '') if hasattr(c, 'metadata') else c.get('section_title', '')
            source = getattr(c, 'metadata', {}).get('source_file', '') if hasattr(c, 'metadata') else c.get('source_file', '')
            content = c.content if hasattr(c, 'content') else c.get('content', '')
            # 标注来源文档
            source_label = source.replace('_refined.md', '').replace('.md', '') if source else ''
            if source_label:
                parts.append("【资料%d·来源：%s】%s\n%s" % (i + 1, source_label, title, content))
            else:
                parts.append("【资料%d】%s\n%s" % (i + 1, title, content))
        return "\n\n".join(parts)

    def generate(self, query: str, contexts: list, language: str = "zh") -> str:
        """根据检索结果生成回答。"""
        context_text = self._build_context(contexts)
        prompt = SYSTEM_PROMPT_EN if language == "en" else SYSTEM_PROMPT_ZH

        if language == "en":
            user_prompt = "Reference materials:\n%s\n\nQuestion: %s" % (context_text, query)
        else:
            user_prompt = "参考资料：\n%s\n\n问题：%s" % (context_text, query)

        last_err = None
        for attempt in range(3):
            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {'role': 'system', 'content': prompt},
                        {'role': 'user', 'content': user_prompt},
                    ],
                    temperature=0.1,
                    max_tokens=800,
                    timeout=15.0,
                )
                answer = resp.choices[0].message.content.strip()
                logger.info('LLM 回答生成完成: %d 字', len(answer))
                return answer
            except Exception as e:
                last_err = e
                if attempt < 2:
                    wait = (attempt + 1) * 0.5
                    logger.warning('LLM 调用失败 (第%d次)，%.1fs 后重试: %s', attempt + 1, wait, str(e)[:80])
                    _time.sleep(wait)
        raise last_err

    def generate_stream(self, query: str, contexts: list, language: str = "zh"):
        """流式生成回答。"""
        context_text = self._build_context(contexts)
        prompt = SYSTEM_PROMPT_EN if language == "en" else SYSTEM_PROMPT_ZH

        if language == "en":
            user_prompt = "Reference materials:\n%s\n\nQuestion: %s" % (context_text, query)
        else:
            user_prompt = "参考资料：\n%s\n\n问题：%s" % (context_text, query)

        messages = [
            {'role': 'system', 'content': prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        last_err = None
        for attempt in range(3):
            try:
                stream = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=800,
                    stream=True,
                )
                for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
                return
            except Exception as e:
                last_err = e
                if attempt < 2:
                    wait = (attempt + 1) * 1.0
                    logger.warning('LLM 流式调用失败 (第%d次)，%.1fs 后重试: %s', attempt + 1, wait, str(e)[:80])
                    _time.sleep(wait)
                else:
                    logger.error('LLM 流式调用最终失败: %s', str(e))
        yield f"[Error: {str(last_err)}]"