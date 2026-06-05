"""问答路由（查询、流式、对比、分析）

核心逻辑：双路召回 -> RRF融合 -> LLM生成
优化目标：响应时间 < 3 秒
"""
import json
import logging
import os
import time
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import APIRouter
from fastapi.responses import StreamingResponse, JSONResponse

from api.models import QueryRequest, QueryResponse, QueryAnalysisResponse, CompareResponse
from api.cache import get_cache_key, cache_get, cache_set
from api.init import get_components

logger = logging.getLogger(__name__)
router = APIRouter()

_GREETING_PATTERNS = [
    '你好', '您好', '嗨', '哈哈', 'hello', 'hi', 'hey',
    '谢谢', '感谢', 'thanks', 'thank you',
    '再见', '拜拜', 'bye', 'goodbye',
    '你是谁', '你是谁啊', '你叫什么', '你是什么',
    '能做什么', '你能做什么', '怎么用', '怎么使用',
    '早上好', '下午好', '晚上好', '晚安',
    '好的', '知道了', '明白', 'ok', 'okay',
]


def _is_greeting(question: str) -> bool:
    q = question.strip().lower().rstrip('。？！?.')
    return q in _GREETING_PATTERNS


def _build_context_from_results(results: list) -> list:
    contexts = []
    for r in results:
        ctx = type('Ctx', (), {
            'content': r['content'],
            'metadata': {
                'section_title': r.get('section_title', ''),
                'source_file': r.get('source_file', ''),
            }
        })()
        contexts.append(ctx)
    return contexts


def _search(comp: dict, question: str, top_k: int, language: str = "zh"):
    """快速检索：Embedding + BM25 并行，RRF 融合，不走 Query Understanding"""
    retriever = comp['retriever']
    embedder = comp['embedder']

    # Embedding 和 BM25 并行执行
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_vec = executor.submit(embedder.encode, [question])
        query_vec = future_vec.result()[0]

    # 向量检索 + BM25 并行
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_dense = executor.submit(retriever._vs.search, query_vec, top_k * 3)
        future_sparse = executor.submit(retriever._bm25.search, question, top_k * 4)
        dense = future_dense.result()
        sparse = future_sparse.result()

    # RRF 融合
    merged = retriever._merge(dense, sparse)



    return merged[:top_k]


def _format_sources(sources: list) -> list:
    return [{'chunk_id': r['chunk_id'], 'section_title': r.get('section_title', ''),
             'source_file': r.get('source_file', ''),
             'content': r['content'][:200]} for r in sources]


def _format_analysis(analysis) -> dict:
    return {
        'intent': analysis.intent, 'intent_description': analysis.intent_description,
        'disambiguated_query': analysis.disambiguated_query, 'sub_queries': analysis.sub_queries,
        'keywords': analysis.keywords, 'confidence': analysis.confidence,
    }


def _quick_analysis(question: str) -> dict:
    """快速分析：不调用 LLM，只做简单判断"""
    q = question.strip().lower()
    if any(w in q for w in ['哪些', '列举', '几个', 'list', 'what are']):
        intent, desc = 'list', 'list question'
    elif any(w in q for w in ['比较', '区别', '对比', 'vs', 'compare']):
        intent, desc = 'comparison', 'comparison question'
    elif any(w in q for w in ['总结', '概括', 'summarize']):
        intent, desc = 'summary', 'summary question'
    elif any(w in q for w in ['为什么', '原因', 'why', 'how']):
        intent, desc = 'explanation', 'explanation question'
    else:
        intent, desc = 'factoid', 'factoid question'

    return {
        'intent': intent, 'intent_description': desc,
        'disambiguated_query': question, 'sub_queries': [question],
        'keywords': [], 'confidence': 0.8,
    }


@router.post('/query/analyze', response_model=QueryAnalysisResponse)
async def analyze_query(req: QueryRequest):
    comp = get_components()
    analysis = comp['query_understanding'].analyze(req.question)
    return QueryAnalysisResponse(
        original_query=analysis.original_query,
        intent=analysis.intent,
        intent_description=analysis.intent_description,
        disambiguated_query=analysis.disambiguated_query,
        sub_queries=analysis.sub_queries,
        keywords=analysis.keywords,
        confidence=analysis.confidence,
    )


@router.post('/query', response_model=QueryResponse)
async def query(req: QueryRequest):
    cache_key = get_cache_key(req.question, req.top_k, req.language)
    cached = cache_get(cache_key)
    if cached:
        return QueryResponse(**cached)

    comp = get_components()

    if _is_greeting(req.question):
        answer = '你好！有什么可以帮你的吗？'
        return QueryResponse(answer=answer, sources=[], query_analysis=_quick_analysis(req.question))

    # 快速检索
    results = _search(comp, req.question, req.top_k, req.language)
    contexts = _build_context_from_results(results)
    answer = comp['generator'].generate(req.question, contexts, req.language)

    sources = _format_sources(results)
    qa = _quick_analysis(req.question)
    cache_set(cache_key, {'answer': answer, 'sources': sources, 'query_analysis': qa})
    return QueryResponse(answer=answer, sources=sources, query_analysis=qa)


@router.post('/query/compare', response_model=CompareResponse)
async def query_compare(req: QueryRequest):
    comp = get_components()
    start = time.time()

    results = _search(comp, req.question, req.top_k, req.language)
    contexts = _build_context_from_results(results)
    rag_answer = comp['generator'].generate(req.question, contexts, req.language)
    llm_answer = comp['generator'].generate(req.question, [], req.language)

    elapsed = int((time.time() - start) * 1000)
    return CompareResponse(
        rag_answer=rag_answer,
        rag_sources=_format_sources(results),
        llm_answer=llm_answer, response_time_ms=elapsed,
    )


@router.post("/query/stream")
async def query_stream(req: QueryRequest):
    comp = get_components()

    if _is_greeting(req.question):
        async def greet_stream():
            yield f"data: {json.dumps({'type': 'token', 'data': '你好！有什么可以帮你的吗？'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(greet_stream(), media_type="text/event-stream")

    # 快速检索
    results = _search(comp, req.question, req.top_k, req.language)
    contexts = _build_context_from_results(results)

    sources = _format_sources(results)
    qa = _quick_analysis(req.question)

    async def generate():
        yield f"data: {json.dumps({'type': 'sources', 'data': sources}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'query_analysis', 'data': qa}, ensure_ascii=False)}\n\n"

        for token in comp["generator"].generate_stream(req.question, contexts, req.language):
            yield f"data: {json.dumps({'type': 'token', 'data': token}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")