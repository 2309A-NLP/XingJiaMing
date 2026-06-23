"""RAG 评估路由"""
import logging
import time

from fastapi import APIRouter

from api.init import get_components

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_percentile(report, primary_name: str, fallback_name: str = None, default: float = 0.0) -> float:
    if hasattr(report, primary_name):
        return round(float(getattr(report, primary_name)), 1)
    if fallback_name and hasattr(report, fallback_name):
        return round(float(getattr(report, fallback_name)), 1)
    return round(default, 1)


@router.post("/evaluate")
async def run_evaluation(config: dict = None):
    """运行 RAG 检索质量评估"""
    from scripts.pipeline.rag_evaluator import RAGEvaluator

    comp = get_components()
    config = config or {}
    top_k = config.get("top_k", 5)
    language = config.get("language", "zh")
    search_mode = config.get("search_mode", "hybrid")

    def query_fn(question: str, top_k: int, language: str):
        from api.models import QueryRequest
        from api.routes.query import _build_context_from_results, _quick_analysis, _search

        req = QueryRequest(question=question, top_k=top_k, language=language, search_mode=search_mode)
        timings = {
            "cache_lookup": 0.0,
            "history_load": 0.0,
            "embedding": 0.0,
            "vector_search": 0.0,
            "bm25_search": 0.0,
            "merge": 0.0,
            "rerank": 0.0,
            "context_build": 0.0,
            "llm_ttft": 0.0,
            "llm_total": 0.0,
            "total": 0.0,
        }

        start = time.perf_counter()
        results = _search(comp, req, timings)
        contexts = _build_context_from_results(results)
        answer = comp["generator"].generate(question, contexts, language)
        elapsed = (time.perf_counter() - start) * 1000

        sources = [
            {
                "chunk_id": item["chunk_id"],
                "section_title": item.get("section_title", ""),
                "source_file": item.get("source_file", ""),
                "content": item["content"][:200],
            }
            for item in results
        ]

        return answer, sources, elapsed

    evaluator = RAGEvaluator()
    report = evaluator.evaluate(query_fn, top_k, language)

    return {
        "total_questions": report.total_questions,
        "avg_precision": round(report.avg_precision, 3),
        "avg_recall": round(report.avg_recall, 3),
        "avg_response_time_ms": round(report.avg_response_time_ms, 1),
        "precision_at_90": round(report.precision_at_90, 3),
        "recall_at_95": round(report.recall_at_95, 3),
        "response_time_under_3s": round(report.response_time_under_3s, 3),
        "p50_response_time_ms": _get_percentile(report, "p50_response_time_ms", "latency_p50_ms"),
        "p95_response_time_ms": _get_percentile(report, "p95_response_time_ms", "latency_p95_ms"),
        "p99_response_time_ms": _get_percentile(report, "p99_response_time_ms", "latency_p99_ms"),
        "under_3s_rate": round(float(getattr(report, "under_3s_rate", report.response_time_under_3s)), 3),
        "category_scores": report.category_scores,
        "details": [
            {
                "question": result.question,
                "precision": round(result.precision, 3),
                "recall": round(result.recall, 3),
                "response_time_ms": round(result.response_time_ms, 1),
                "keyword_hits": result.keyword_hits,
                "keyword_total": result.keyword_total,
            }
            for result in report.results
        ],
    }
