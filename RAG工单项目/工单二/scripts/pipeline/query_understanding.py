"""Query 理解模块

工单编号：人工智能 NLP-RAG-基于 PDF 文档的问答系统

功能：
1. 意图识别：识别用户问题的核心意图
2. 消歧：处理多义词或模糊表述，确保问题的准确性
3. 分解与抽象：将复杂问题分解为多个子问题，提取关键信息
"""
from __future__ import annotations
import logging
import json
import os
from typing import List, Dict, Optional
from dataclasses import dataclass
from openai import OpenAI

logger = logging.getLogger(__name__)


@dataclass
class QueryAnalysis:
    """Query 分析结果"""
    original_query: str           # 原始问题
    intent: str                   # 意图类型
    intent_description: str       # 意图描述
    disambiguated_query: str      # 消歧后的问题
    sub_queries: List[str]        # 分解后的子问题
    keywords: List[str]           # 关键词
    confidence: float             # 置信度


class QueryUnderstanding:
    """Query 理解器
    
    使用 LLM 进行意图识别、消歧和分解。
    """
    
    # 意图类型定义
    INTENT_TYPES = {
        'factoid': '事实性问题 - 询问具体事实、数据、名称',
        'comparison': '比较性问题 - 比较两个或多个对象',
        'summary': '总结性问题 - 要求概括或总结',
        'explanation': '解释性问题 - 要求解释原因或机制',
        'list': '列举性问题 - 要求列出多个项目',
        'definition': '定义性问题 - 询问定义或概念',
        'temporal': '时间性问题 - 询问时间、日期、时期',
        'quantitative': '数量性问题 - 询问数字、金额、比例',
        'other': '其他类型问题',
    }
    
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        self._client = OpenAI(
            api_key=api_key or os.getenv('MIMO_API_KEY'),
            base_url=base_url or os.getenv('MIMO_BASE_URL'),
        )
        self._model = model or os.getenv('MIMO_MODEL', 'deepseek-chat')
        logger.info('Query 理解器初始化完成')
    
    def analyze(self, query: str) -> QueryAnalysis:
        """分析用户问题
        
        Args:
            query: 用户问题
            
        Returns:
            QueryAnalysis: 分析结果
        """
        logger.info('开始分析问题: %s', query)
        
        # 构建 prompt
        prompt = self._build_analysis_prompt(query)
        
        try:
            # 调用 LLM
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {'role': 'system', 'content': self._get_system_prompt()},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=0.1,  # 低温度，保证稳定性
                max_tokens=1000,
            )
            
            result_text = response.choices[0].message.content.strip()
            logger.info('LLM 返回: %s', result_text[:200])
            
            # 解析结果
            analysis = self._parse_result(query, result_text)
            logger.info('分析完成: intent=%s, sub_queries=%d', 
                       analysis.intent, len(analysis.sub_queries))
            return analysis
            
        except Exception as e:
            logger.error('Query 分析失败: %s', str(e))
            # 返回默认结果
            return QueryAnalysis(
                original_query=query,
                intent='other',
                intent_description='无法识别',
                disambiguated_query=query,
                sub_queries=[query],
                keywords=[],
                confidence=0.0
            )
    
    def _get_system_prompt(self) -> str:
        """获取系统提示词"""
        return """你是一个专业的 Query 理解助手。你的任务是分析用户的问题，提取关键信息。

你需要完成以下任务：
1. **意图识别**：判断问题属于哪种类型
2. **消歧**：如果问题有歧义，给出明确的表述
3. **分解与抽象**：将复杂问题分解为多个简单的子问题

请用 JSON 格式返回结果，格式如下：
{
    "intent": "意图类型",
    "intent_description": "意图描述",
    "disambiguated_query": "消歧后的问题",
    "sub_queries": ["子问题1", "子问题2"],
    "keywords": ["关键词1", "关键词2"],
    "confidence": 0.95
}

意图类型包括：
- factoid: 事实性问题（询问具体事实、数据、名称）
- comparison: 比较性问题（比较两个或多个对象）
- summary: 总结性问题（要求概括或总结）
- explanation: 解释性问题（要求解释原因或机制）
- list: 列举性问题（要求列出多个项目）
- definition: 定义性问题（询问定义或概念）
- temporal: 时间性问题（询问时间、日期、时期）
- quantitative: 数量性问题（询问数字、金额、比例）
- other: 其他类型

注意：
- 如果问题本身已经很清晰，disambiguated_query 可以和原问题一样
- 如果问题很简单，sub_queries 只需要一个元素（原问题）
- keywords 应该提取问题中的核心实体和概念
- confidence 表示你对分析结果的信心（0-1）"""
    
    def _build_analysis_prompt(self, query: str) -> str:
        """构建分析提示词"""
        return f"""请分析以下用户问题：

用户问题：{query}

请按照要求返回 JSON 格式的分析结果。"""
    
    def _parse_result(self, original_query: str, result_text: str) -> QueryAnalysis:
        """解析 LLM 返回的结果"""
        try:
            # 尝试提取 JSON
            json_str = self._extract_json(result_text)
            data = json.loads(json_str)
            
            # 验证并修正
            intent = data.get('intent', 'other')
            if intent not in self.INTENT_TYPES:
                intent = 'other'
            
            return QueryAnalysis(
                original_query=original_query,
                intent=intent,
                intent_description=data.get('intent_description', ''),
                disambiguated_query=data.get('disambiguated_query', original_query),
                sub_queries=data.get('sub_queries', [original_query]),
                keywords=data.get('keywords', []),
                confidence=float(data.get('confidence', 0.5))
            )
            
        except Exception as e:
            logger.warning('解析结果失败: %s', str(e))
            # 返回默认结果
            return QueryAnalysis(
                original_query=original_query,
                intent='other',
                intent_description='解析失败',
                disambiguated_query=original_query,
                sub_queries=[original_query],
                keywords=[],
                confidence=0.0
            )
    
    def _extract_json(self, text: str) -> str:
        """从文本中提取 JSON"""
        # 尝试直接解析
        try:
            json.loads(text)
            return text
        except:
            pass
        
        # 尝试提取 ```json ... ```
        import re
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            return json_match.group(1)
        
        # 尝试提取 { ... }
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json_match.group(0)
        
        raise ValueError('无法提取 JSON')
    
    def get_search_queries(self, analysis: QueryAnalysis) -> List[str]:
        """根据分析结果获取搜索查询
        
        Args:
            analysis: 分析结果
            
        Returns:
            搜索查询列表
        """
        queries = []
        
        # 1. 添加消歧后的问题
        queries.append(analysis.disambiguated_query)
        
        # 2. 添加子问题
        for sq in analysis.sub_queries:
            if sq not in queries:
                queries.append(sq)
        
        # 3. 添加关键词组合
        if analysis.keywords:
            keyword_query = ' '.join(analysis.keywords)
            if keyword_query not in queries:
                queries.append(keyword_query)
        
        return queries


# 全局单例
_query_understanding = None


def get_query_understanding() -> QueryUnderstanding:
    """获取 Query 理解器单例"""
    global _query_understanding
    if _query_understanding is None:
        _query_understanding = QueryUnderstanding()
    return _query_understanding
