"""RAG 评估路由"""
import logging
import time
from fastapi import APIRouter
from api.init import get_components

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/evaluate")
async def run_evaluation(config: dict = None):
    """运行 RAG 检索质量评估

    config: 可选配置，如 {"top_k": 5, "language": "zh", "search_mode": "hybrid"}
    """
    from scripts.pipeline.rag_evaluator import RAGEvaluator

    comp = get_components()
    config = config or {}
    top_k = config.get('top_k', 5)
    language = config.get('language', 'zh')
    search_mode = config.get('search_mode', 'hybrid')

    # 构造查询函数
    def query_fn(question: str, top_k: int, language: str):
        from api.routes.query import _search, _build_context_from_results, _quick_analysis
        from api.models import QueryRequest

        start = time.time()
        mock_req = QueryRequest(question=question, top_k=top_k, language=language, search_mode=search_mode)
        results = _search(comp, mock_req)
        contexts = _build_context_from_results(results)
        answer = comp['generator'].generate(question, contexts, language)
        elapsed = (time.time() - start) * 1000

        sources = [{
            'chunk_id': r['chunk_id'],
            'section_title': r.get('section_title', ''),
            'source_file': r.get('source_file', ''),
            'content': r['content'][:200],
        } for r in results]

        return answer, sources, elapsed

    evaluator = RAGEvaluator()
    report = evaluator.evaluate(query_fn, top_k, language)

    return {
        'total_questions': report.total_questions,
        'avg_precision': round(report.avg_precision, 3),
        'avg_recall': round(report.avg_recall, 3),
        'avg_response_time_ms': round(report.avg_response_time_ms, 1),
        'precision_at_90': round(report.precision_at_90, 3),
        'recall_at_95': round(report.recall_at_95, 3),
        'response_time_under_3s': round(report.response_time_under_3s, 3),
        'category_scores': report.category_scores,
        'details': [
            {
                'question': r.question,
                'precision': round(r.precision, 3),
                'recall': round(r.recall, 3),
                'response_time_ms': round(r.response_time_ms, 1),
                'keyword_hits': r.keyword_hits,
                'keyword_total': r.keyword_total,
            }
            for r in report.results
        ]
    }
