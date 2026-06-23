"""RAG retrieval quality evaluator."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List

logger = logging.getLogger(__name__)


@dataclass
class TestCase:
    question: str
    expected_keywords: List[str]
    expected_sources: List[str] = field(default_factory=list)
    category: str = "general"


@dataclass
class EvalResult:
    question: str
    answer: str
    sources: List[dict]
    response_time_ms: float
    keyword_hits: int
    keyword_total: int
    source_hits: int
    source_total: int
    precision: float = 0.0
    recall: float = 0.0


@dataclass
class EvalReport:
    total_questions: int = 0
    avg_response_time_ms: float = 0.0
    avg_precision: float = 0.0
    avg_recall: float = 0.0
    precision_at_90: float = 0.0
    recall_at_95: float = 0.0
    response_time_under_3s: float = 0.0
    p50_response_time_ms: float = 0.0
    p95_response_time_ms: float = 0.0
    p99_response_time_ms: float = 0.0
    under_3s_rate: float = 0.0
    results: List[EvalResult] = field(default_factory=list)
    category_scores: Dict[str, dict] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            "=" * 50,
            "  RAG 检索质量评估报告",
            "=" * 50,
            f"  测试问题数:     {self.total_questions}",
            "",
            "  📊 核心指标:",
            f"     平均准确率:    {self.avg_precision * 100:>5.1f}%  (目标: 90%)",
            f"     平均召回率:    {self.avg_recall * 100:>5.1f}%  (目标: 95%)",
            f"     平均响应时间:  {self.avg_response_time_ms:>7.0f}ms (目标: <3000ms)",
            "",
            "  📈 达标情况:",
            f"     准确率 ≥90%:   {self.precision_at_90 * 100:>5.1f}% 的问题",
            f"     召回率 ≥95%:   {self.recall_at_95 * 100:>5.1f}% 的问题",
            f"     响应 <3s:      {self.response_time_under_3s * 100:>5.1f}% 的问题",
            f"     P50 / P95 / P99: {self.p50_response_time_ms:.0f} / {self.p95_response_time_ms:.0f} / {self.p99_response_time_ms:.0f} ms",
        ]
        if self.category_scores:
            lines.append("")
            lines.append("  📋 分类得分:")
            for category, scores in self.category_scores.items():
                lines.append(
                    f"     {category}: P={scores['precision'] * 100:.0f}% R={scores['recall'] * 100:.0f}% T={scores['time']:.0f}ms"
                )
        lines.append("=" * 50)
        return "\n".join(lines)


DEFAULT_TEST_CASES = [
    TestCase(question="公司的主营业务是什么？", expected_keywords=["主营业务", "收入", "产品"], category="business"),
    TestCase(question="公司的主要客户有哪些？", expected_keywords=["客户", "前五", "销售"], category="business"),
    TestCase(question="公司面临哪些经营风险？", expected_keywords=["风险", "经营"], category="risk"),
    TestCase(question="公司的核心竞争力是什么？", expected_keywords=["核心", "竞争", "优势"], category="business"),
    TestCase(question="公司的注册资本是多少？", expected_keywords=["注册资本", "万元"], category="financial"),
    TestCase(question="公司的股东结构是怎样的？", expected_keywords=["股东", "持股", "比例"], category="structure"),
    TestCase(question="公司的员工人数有多少？", expected_keywords=["员工", "人"], category="hr"),
    TestCase(question="公司的主要产品有哪些？", expected_keywords=["产品", "主要"], category="business"),
]


def _percentile(values: List[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * ratio))))
    return float(ordered[index])


class RAGEvaluator:
    """Evaluate retrieval quality and latency for a fixed question set."""

    def __init__(self, test_cases: List[TestCase] = None, cases_file: str = None):
        if test_cases:
            self._cases = test_cases
        elif cases_file and os.path.exists(cases_file):
            self._cases = self._load_cases(cases_file)
        else:
            self._cases = DEFAULT_TEST_CASES

    def _load_cases(self, filepath: str) -> List[TestCase]:
        with open(filepath, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return [
            TestCase(
                question=item["question"],
                expected_keywords=item.get("expected_keywords", []),
                expected_sources=item.get("expected_sources", []),
                category=item.get("category", "general"),
            )
            for item in data
        ]

    def evaluate(self, query_fn, top_k: int = 5, language: str = "zh") -> EvalReport:
        report = EvalReport()
        results: List[EvalResult] = []
        category_data: Dict[str, dict] = {}

        for case in self._cases:
            logger.info("评估问题: %s", case.question)
            try:
                answer, sources, resp_time = query_fn(case.question, top_k, language)
            except Exception as exc:
                logger.error("查询失败: %s -> %s", case.question, exc)
                continue

            keyword_hits = sum(1 for keyword in case.expected_keywords if keyword in answer)
            keyword_total = len(case.expected_keywords)
            precision = keyword_hits / max(keyword_total, 1)

            source_hits = 0
            if case.expected_sources:
                source_files = {
                    item.get("source_file", "")
                    for item in sources
                    if isinstance(item, dict)
                }
                for expected in case.expected_sources:
                    if any(expected in source_file for source_file in source_files):
                        source_hits += 1
                source_total = len(case.expected_sources)
                recall = source_hits / max(source_total, 1)
            else:
                source_total = 0
                recall = 1.0 if len(sources) > 0 else 0.0

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

            category = case.category
            if category not in category_data:
                category_data[category] = {"precisions": [], "recalls": [], "times": []}
            category_data[category]["precisions"].append(precision)
            category_data[category]["recalls"].append(recall)
            category_data[category]["times"].append(resp_time)

        report.total_questions = len(results)
        report.results = results

        if results:
            latencies = [item.response_time_ms for item in results]
            report.avg_precision = sum(item.precision for item in results) / len(results)
            report.avg_recall = sum(item.recall for item in results) / len(results)
            report.avg_response_time_ms = sum(latencies) / len(latencies)
            report.precision_at_90 = sum(1 for item in results if item.precision >= 0.9) / len(results)
            report.recall_at_95 = sum(1 for item in results if item.recall >= 0.95) / len(results)
            report.response_time_under_3s = sum(1 for item in results if item.response_time_ms < 3000) / len(results)
            report.p50_response_time_ms = _percentile(latencies, 0.50)
            report.p95_response_time_ms = _percentile(latencies, 0.95)
            report.p99_response_time_ms = _percentile(latencies, 0.99)
            report.under_3s_rate = report.response_time_under_3s

        for category, data in category_data.items():
            report.category_scores[category] = {
                "precision": sum(data["precisions"]) / len(data["precisions"]),
                "recall": sum(data["recalls"]) / len(data["recalls"]),
                "time": sum(data["times"]) / len(data["times"]),
            }

        return report

    def evaluate_search_modes(self, query_fn_factory, modes: List[dict]) -> Dict[str, EvalReport]:
        reports = {}
        for mode in modes:
            name = mode.get("name", "unknown")
            logger.info("评估策略: %s", name)
            reports[name] = self.evaluate(query_fn_factory(mode))
        return reports
