"""查询改写（Query Rewriting）

用规则做基础改写，不依赖 LLM（避免 LLM 不稳定问题）。
"""
from __future__ import annotations
import logging
import re
from typing import List

logger = logging.getLogger(__name__)

# 关键词扩展映射
EXPAND_MAP = {
    '怎么样': ['主营业务', '财务状况', '核心竞争力', '行业地位'],
    '风险': ['经营风险', '财务风险', '技术风险', '市场风险'],
    '发行': ['发行股票数量', '发行价格', '发行时间', '上市交易所'],
    '财务': ['营业收入', '净利润', '资产负债', '现金流'],
    '业务': ['主营业务', '产品结构', '客户情况', '市场占有率'],
    '股东': ['控股股东', '实际控制人', '持股比例', '股东结构'],
}


class QueryRewriter:
    """规则 + LLM 混合查询改写。"""

    def __init__(self, use_llm: bool = False, api_key: str = None,
                 base_url: str = None, model: str = None):
        self._use_llm = use_llm
        if use_llm:
            from openai import OpenAI
            import os
            self._client = OpenAI(
                api_key=api_key or os.getenv('MIMO_API_KEY'),
                base_url=base_url or os.getenv('MIMO_BASE_URL'),
            )
            self._model = model or os.getenv('MIMO_MODEL', 'mimo-v2.5')

    def rewrite(self, query: str) -> List[str]:
        """改写用户问题。"""
        # 规则改写
        expanded = self._rule_expand(query)
        if len(expanded) > 1:
            logger.info('规则改写: [%s] -> %s', query, expanded)
            return expanded

        # 问题已经够具体，不改写
        if len(query) >= 8:
            logger.info('问题已具体，不改写: [%s]', query)
            return [query]

        # 短问题用 LLM 改写（如果启用）
        if self._use_llm:
            return self._llm_rewrite(query)

        return [query]

    def _rule_expand(self, query: str) -> List[str]:
        """用关键词映射做规则扩展。"""
        results = []
        for keyword, expansions in EXPAND_MAP.items():
            if keyword in query:
                for exp in expansions:
                    results.append(query.replace(keyword, exp))
        return results if results else [query]

    def _llm_rewrite(self, query: str) -> List[str]:
        """用 LLM 改写（备用）。"""
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {'role': 'system', 'content': '把问题改写为1-3个检索词，每行一个，不要解释。'},
                    {'role': 'user', 'content': query},
                ],
                temperature=0.1,
                max_tokens=500,
            )
            text = resp.choices[0].message.content.strip()
            queries = [q.strip() for q in text.split('\n') if q.strip() and len(q.strip()) > 1]
            return queries if queries else [query]
        except Exception as e:
            logger.warning('LLM 改写失败: %s', e)
            return [query]

