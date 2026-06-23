"""Query understanding with an optional LLM backend."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import List

from openai import OpenAI

logger = logging.getLogger(__name__)


@dataclass
class QueryAnalysis:
    original_query: str
    intent: str
    intent_description: str
    disambiguated_query: str
    sub_queries: List[str]
    keywords: List[str]
    confidence: float


class QueryUnderstanding:
    """Analyze user questions with graceful fallback when no LLM key is configured."""

    INTENT_TYPES = {
        "factoid": "事实性问题",
        "comparison": "比较性问题",
        "summary": "总结性问题",
        "explanation": "解释性问题",
        "list": "列举性问题",
        "definition": "定义性问题",
        "temporal": "时间性问题",
        "quantitative": "数量性问题",
        "other": "其他类型问题",
    }

    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        resolved_api_key = api_key or os.getenv("MIMO_API_KEY")
        resolved_base_url = base_url or os.getenv("MIMO_BASE_URL")
        self._client = None
        if resolved_api_key:
            self._client = OpenAI(api_key=resolved_api_key, base_url=resolved_base_url)
        else:
            logger.warning("MIMO_API_KEY 未配置，Query 理解将退化为规则模式")
        self._model = model or os.getenv("MIMO_MODEL", "deepseek-chat")
        logger.info("Query 理解器初始化完成")

    def analyze(self, query: str) -> QueryAnalysis:
        logger.info("开始分析问题: %s", query)
        if self._client is None:
            return self._fallback_analysis(query, confidence=0.5)

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": self._build_analysis_prompt(query)},
                ],
                temperature=0.1,
                max_tokens=1000,
            )
            result_text = (response.choices[0].message.content or "").strip()
            logger.info("LLM 返回: %s", result_text[:200])
            return self._parse_result(query, result_text)
        except Exception as exc:
            logger.error("Query 分析失败: %s", str(exc))
            return self._fallback_analysis(query, confidence=0.0)

    def _fallback_analysis(self, query: str, confidence: float) -> QueryAnalysis:
        lowered = query.lower()
        if any(token in lowered for token in ("比较", "区别", "对比", "vs", "compare")):
            intent = "comparison"
        elif any(token in lowered for token in ("哪些", "列举", "几个", "list")):
            intent = "list"
        elif any(token in lowered for token in ("总结", "概括", "summarize")):
            intent = "summary"
        elif any(token in lowered for token in ("为什么", "如何", "how", "why")):
            intent = "explanation"
        else:
            intent = "factoid"

        return QueryAnalysis(
            original_query=query,
            intent=intent,
            intent_description=self.INTENT_TYPES.get(intent, self.INTENT_TYPES["other"]),
            disambiguated_query=query,
            sub_queries=[query],
            keywords=[],
            confidence=confidence,
        )

    def _get_system_prompt(self) -> str:
        return """你是一个专业的 Query 理解助手。

请输出 JSON，字段包括：
intent, intent_description, disambiguated_query, sub_queries, keywords, confidence
"""

    def _build_analysis_prompt(self, query: str) -> str:
        return f"请分析以下用户问题，并返回 JSON：\n\n用户问题：{query}"

    def _parse_result(self, original_query: str, result_text: str) -> QueryAnalysis:
        try:
            json_str = self._extract_json(result_text)
            data = json.loads(json_str)
            intent = data.get("intent", "other")
            if intent not in self.INTENT_TYPES:
                intent = "other"
            return QueryAnalysis(
                original_query=original_query,
                intent=intent,
                intent_description=data.get("intent_description", self.INTENT_TYPES[intent]),
                disambiguated_query=data.get("disambiguated_query", original_query),
                sub_queries=data.get("sub_queries", [original_query]) or [original_query],
                keywords=data.get("keywords", []),
                confidence=float(data.get("confidence", 0.5)),
            )
        except Exception as exc:
            logger.warning("解析结果失败: %s", str(exc))
            return self._fallback_analysis(original_query, confidence=0.0)

    def _extract_json(self, text: str) -> str:
        try:
            json.loads(text)
            return text
        except Exception:
            pass

        import re

        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if fenced:
            return fenced.group(1)

        inline = re.search(r"\{.*\}", text, re.DOTALL)
        if inline:
            return inline.group(0)

        raise ValueError("无法提取 JSON")

    def get_search_queries(self, analysis: QueryAnalysis) -> List[str]:
        queries = [analysis.disambiguated_query]
        for sub_query in analysis.sub_queries:
            if sub_query not in queries:
                queries.append(sub_query)
        if analysis.keywords:
            keyword_query = " ".join(analysis.keywords)
            if keyword_query not in queries:
                queries.append(keyword_query)
        return queries


_query_understanding = None


def get_query_understanding() -> QueryUnderstanding:
    global _query_understanding
    if _query_understanding is None:
        _query_understanding = QueryUnderstanding()
    return _query_understanding
