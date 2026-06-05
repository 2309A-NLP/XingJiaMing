"""LLM 生成回答"""
from __future__ import annotations
import logging
import os
import time as _time
from typing import List
from openai import OpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_ZH = """你是一个智能文档助手。

你手上有两部分信息：
1. 对话历史：之前和用户的聊天记录（包含用户提到的个人信息，如姓名、身份等）
2. 参考资料：从多份文档中检索到的内容（标注了【来源文档】）

回答时，对话历史中的用户个人信息和参考资料同等重要，都要参考。

【核心规则 - 必须遵守】
1. 回答时优先参考对话历史中用户提供的个人信息（如姓名、身份等），其次参考文档资料
2. 只用参考资料和对话历史里的信息回答，不要添加它们没有的内容
3. 优先使用原文的措辞和表述，不要自己换一种说法
4. 覆盖参考资料中所有与问题相关的要点，不要遗漏
5. 数据必须注明来源或时间段，不要混淆不同年代/期间的数据
6. 不要添加原文没有的定性判断（如"较高""较低"），除非原文明确说了
7. 【重要】仔细阅读参考资料，如果参考资料中有与问题相关的数据或信息，必须回答，不要说"未找到"。只有当参考资料中确实完全没有相关内容时，才可以说"未找到"
8. 闲聊/问候时自然友好回应，不用看资料

【数字提取规则 - 特别重要】
- 从参考资料中提取数字时，必须仔细核对，不要读错行或读错列
- 如果参考资料中有表格，注意区分行列对应关系
- 保留原始数字格式（如 1,379.58 亿元），不要自行换算
- 如果有多个年份的数据，明确说明是哪一年的数据

【管理层问题规则 - 特别重要】
当用户询问董事长、行长、CEO等管理层信息时：
1. 仔细查找参考资料中的表格数据，格式可能是：['姓名','职务','任职状态',...] 或类似的表格格式
2. 注意区分"现任"和"离任"状态，优先回答现任人员
3. 如果有多个时间段的任职信息，明确说明是哪个时间段的
4. 如果参考资料中明确写了"XXX先生/女士，职务"这样的格式，直接引用
5. 不要混淆不同人员的任职信息，确保每个人对应正确的职务
6. 如果问的是某一年的管理层，确保回答的是该年在职的人员
7. 【关键】特别注意以下格式的表格数据：
   - ['谢永林','董事长','现任',...] 表示谢永林是董事长
   - ['胡跃飞','董事、行长','现任',...] 表示胡跃飞是行长
   - 如果看到这样的表格，直接引用其中的信息，不要忽略
8. 如果参考资料中有多个来源提到同一人的职务，以表格数据为准

【多文档规则】
- 如果用户问的是某家公司的信息，只用该公司的文档回答，不要混入其他公司的数据
- 回答时先确认参考资料中是否有该公司名称，如果有再回答
- 如果参考资料中只有其他公司的数据，明确说明"参考资料中未找到[公司名]的数据，但找到了[其他公司]的数据"
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
    def _build_messages(self, prompt: str, user_prompt: str, history: list = None) -> list:
        """构建消息列表，把历史对话插在 system 和当前 user 之间"""
        messages = [{'role': 'system', 'content': prompt}]
        # 插入历史对话（最近 N 轮）
        if history:
            for h in history:
                role = h.get('role', 'user')
                if role in ('user', 'assistant'):
                    messages.append({'role': role, 'content': h.get('content', '')})
        messages.append({'role': 'user', 'content': user_prompt})
        return messages

    def generate(self, query: str, contexts: list, language: str = "zh", history: list = None) -> str:
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
                    messages=self._build_messages(prompt, user_prompt, history),
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

    def generate_stream(self, query: str, contexts: list, language: str = "zh", history: list = None):
        """流式生成回答。"""
        context_text = self._build_context(contexts)
        prompt = SYSTEM_PROMPT_EN if language == "en" else SYSTEM_PROMPT_ZH

        if language == "en":
            user_prompt = "Reference materials:\n%s\n\nQuestion: %s" % (context_text, query)
        else:
            user_prompt = "参考资料：\n%s\n\n问题：%s" % (context_text, query)

        messages = self._build_messages(prompt, user_prompt, history)

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