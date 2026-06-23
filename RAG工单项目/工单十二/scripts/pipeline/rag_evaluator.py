"""RAG 检索质量评估器

评估维度：
  1. 准确率 (Precision): 返回结果中相关文档的比例
  2. 召回率 (Recall): 相关文档被检索到的比例
  3. 响应时间 (Response Time): 从查询到返回的耗时

使用方式：
  准备测试问题集 -> 运行评估 -> 查看报告
"""
from __future__ import annotations
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TestCase:
    """测试用例"""
    question: str                           # 测试问题
    expected_keywords: List[str]            # 期望答案包含的关键词
    expected_sources: List[str] = field(default_factory=list)  # 期望来源文件名
    category: str = "general"               # 问题类别


@dataclass
class EvalResult:
    """单条评估结果"""
    question: str
    answer: str
    sources: List[dict]
    response_time_ms: float
    keyword_hits: int                       # 命中关键词数
    keyword_total: int                      # 总关键词数
    source_hits: int                        # 命中来源数
    source_total: int                       # 总来源数
    precision: float = 0.0                  # 准确率
    recall: float = 0.0                     # 召回率


@dataclass
class EvalReport:
    """评估报告"""
    total_questions: int = 0
    avg_response_time_ms: float = 0.0
    avg_precision: float = 0.0
    avg_recall: float = 0.0
    precision_at_90: float = 0.0            # 准确率 >= 90% 的比例
    recall_at_95: float = 0.0               # 召回率 >= 95% 的比例
    response_time_under_3s: float = 0.0     # 响应时间 < 3s 的比例
    results: List[EvalResult] = field(default_factory=list)
    category_scores: Dict[str, dict] = field(default_factory=dict)

    def summary(self) -> str:
        """生成可读摘要"""
        lines = [
            f"{'='*50}",
            f"  RAG 检索质量评估报告",
            f"{'='*50}",
            f"  测试问题数:     {self.total_questions}",
            f"",
            f"  📊 核心指标:",
            f"     平均准确率:    {self.avg_precision*100:>5.1f}%  (目标: 90%)",
            f"     平均召回率:    {self.avg_recall*100:>5.1f}%  (目标: 95%)",
            f"     平均响应时间:  {self.avg_response_time_ms:>7.0f}ms (目标: <3000ms)",
            f"",
            f"  📈 达标情况:",
            f"     准确率 ≥90%:   {self.precision_at_90*100:>5.1f}% 的问题",
            f"     召回率 ≥95%:   {self.recall_at_95*100:>5.1f}% 的问题",
            f"     响应 <3s:      {self.response_time_under_3s*100:>5.1f}% 的问题",
        ]
        if self.category_scores:
            lines.append(f"")
            lines.append(f"  📋 分类得分:")
            for cat, scores in self.category_scores.items():
                lines.append(f"     {cat}: P={scores['precision']*100:.0f}% R={scores['recall']*100:.0f}% T={scores['time']:.0f}ms")
        lines.append(f"{'='*50}")
        return "\n".join(lines)


# 默认测试问题集（基于招股说明书场景）
DEFAULT_TEST_CASES = [
    TestCase(
        question="公司的主营业务是什么？",
        expected_keywords=["主营业务", "收入", "产品"],
        category="business"
    ),
    TestCase(
        question="公司的主要客户有哪些？",
        expected_keywords=["客户", "前五", "销售"],
        category="business"
    ),
    TestCase(
        question="公司面临哪些经营风险？",
        expected_keywords=["风险", "经营"],
        category="risk"
    ),
    TestCase(
        question="公司的核心竞争力是什么？",
        expected_keywords=["核心", "竞争", "优势"],
        category="business"
    ),
    TestCase(
        question="公司的注册资本是多少？",
        expected_keywords=["注册资本", "万元"],
        category="financial"
    ),
    TestCase(
        question="公司的股东结构是怎样的？",
        expected_keywords=["股东", "持股", "比例"],
        category="structure"
    ),
    TestCase(
        question="公司的员工人数有多少？",
        expected_keywords=["员工", "人"],
        category="hr"
    ),
    TestCase(
        question="公司的主要产品有哪些？",
        expected_keywords=["产品", "主要"],
        category="business"
    ),
]


class RAGEvaluator:
    """RAG 检索质量评估器。

    给定测试问题集，自动运行查询并评估准确率、召回率、响应时间。
    """

    def __init__(self, test_cases: List[TestCase] = None, cases_file: str = None):
        """
        Args:
            test_cases: 测试用例列表。
            cases_file: 测试用例 JSON 文件路径。
        """
        if test_cases:
            self._cases = test_cases
        elif cases_file and os.path.exists(cases_file):
            self._cases = self._load_cases(cases_file)
        else:
            self._cases = DEFAULT_TEST_CASES

    def _load_cases(self, filepath: str) -> List[TestCase]:
        """从 JSON 文件加载测试用例"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cases = []
        for item in data:
            cases.append(TestCase(
                question=item['question'],
                expected_keywords=item.get('expected_keywords', []),
                expected_sources=item.get('expected_sources', []),
                category=item.get('category', 'general'),
            ))
        return cases

    def evaluate(self, query_fn, top_k: int = 5, language: str = "zh") -> EvalReport:
        """运行评估

        Args:
            query_fn: 查询函数，签名 (question, top_k, language) -> (answer, sources, response_time_ms)
            top_k: 返回结果数。
            language: 语言。

        Returns:
            评估报告。
        """
        report = EvalReport()
        results = []
        category_data = {}

        for case in self._cases:
            logger.info('评估问题: %s', case.question)
            start = time.time()

            try:
                answer, sources, resp_time = query_fn(case.question, top_k, language)
            except Exception as e:
                logger.error('查询失败: %s -> %s', case.question, e)
                continue

            # 计算关键词命中（准确率的代理指标）
            keyword_hits = 0
            for kw in case.expected_keywords:
                if kw in answer:
                    keyword_hits += 1
            keyword_total = len(case.expected_keywords)
            precision = keyword_hits / max(keyword_total, 1)

            # 计算来源命中（召回率的代理指标）
            source_hits = 0
            if case.expected_sources:
                source_files = set()
                for s in sources:
                    if isinstance(s, dict):
                        source_files.add(s.get('source_file', ''))
                for expected in case.expected_sources:
                    if any(expected in sf for sf in source_files):
                        source_hits += 1
                source_total = len(case.expected_sources)
                recall = source_hits / max(source_total, 1)
            else:
                # 没有指定期望来源时，用"是否返回了结果"作为召回率
                recall = 1.0 if len(sources) > 0 else 0.0
                source_total = 0

            result = EvalResult(
                question=case.question,
                answer=answer[:200],
                sources=sources,
                response_time_ms=resp_time,
                keyword_hits=keyword_hits,
                keyword_total=keyword_total,
                source_hits=source_hits,
                source_total=source_total,
                precision=precision,
                recall=recall,
            )
            results.append(result)

            # 按类别统计
            cat = case.category
            if cat not in category_data:
                category_data[cat] = {'precisions': [], 'recalls': [], 'times': []}
            category_data[cat]['precisions'].append(precision)
            category_data[cat]['recalls'].append(recall)
            category_data[cat]['times'].append(resp_time)

        # 汇总
        report.total_questions = len(results)
        report.results = results

        if results:
            report.avg_precision = sum(r.precision for r in results) / len(results)
            report.avg_recall = sum(r.recall for r in results) / len(results)
            report.avg_response_time_ms = sum(r.response_time_ms for r in results) / len(results)
            report.precision_at_90 = sum(1 for r in results if r.precision >= 0.9) / len(results)
            report.recall_at_95 = sum(1 for r in results if r.recall >= 0.95) / len(results)
            report.response_time_under_3s = sum(1 for r in results if r.response_time_ms < 3000) / len(results)

        # 分类得分
        for cat, data in category_data.items():
            report.category_scores[cat] = {
                'precision': sum(data['precisions']) / len(data['precisions']),
                'recall': sum(data['recalls']) / len(data['recalls']),
                'time': sum(data['times']) / len(data['times']),
            }

        return report

    def evaluate_search_modes(self, query_fn_factory, modes: List[dict]) -> Dict[str, EvalReport]:
        """对比不同检索策略的评估结果

        Args:
            query_fn_factory: 创建查询函数的工厂，签名 (config) -> query_fn
            modes: 检索策略配置列表，每个是 dict

        Returns:
            {策略名称: 评估报告}
        """
        reports = {}
        for mode in modes:
            name = mode.get('name', 'unknown')
            logger.info('评估策略: %s', name)
            query_fn = query_fn_factory(mode)
            reports[name] = self.evaluate(query_fn)
        return reports
