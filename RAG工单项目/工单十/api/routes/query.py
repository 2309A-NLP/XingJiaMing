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
from scripts.memory.session_memory import SessionMemory
from api.init import get_components

logger = logging.getLogger(__name__)
router = APIRouter()

# Redis 短期记忆，给多轮对话提供上下文
session_mem = SessionMemory()

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


def _search(comp: dict, req: 'QueryRequest') -> list:
    """检索函数：支持向量检索、全文检索、混合检索

    Args:
        comp: 组件字典
        req: QueryRequest 对象，包含所有检索参数
    """
    retriever = comp['retriever']
    embedder = comp['embedder']

    # 如果指定了嵌入模型，切换到该模型
    if req.embedding_model and hasattr(embedder, 'switch_model'):
        embedder.switch_model(req.embedding_model)

    # 根据检索模式执行不同的检索策略
    if req.search_mode == "vector":
        # 纯向量检索
        with ThreadPoolExecutor(max_workers=1) as executor:
            future_vec = executor.submit(embedder.encode, [req.question])
            query_vec = future_vec.result()[0]
        results = retriever._vs.search(query_vec, req.top_k * 3)

    elif req.search_mode == "bm25":
        # 纯 BM25 检索
        results = retriever._bm25.search(req.question, req.top_k * 4, match_mode=req.match_mode)

    else:
        # 混合检索（默认）
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_vec = executor.submit(embedder.encode, [req.question])
            query_vec = future_vec.result()[0]

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_dense = executor.submit(retriever._vs.search, query_vec, req.top_k * 3)
            future_sparse = executor.submit(retriever._bm25.search, req.question, req.top_k * 4, match_mode=req.match_mode)
            dense = future_dense.result()
            sparse = future_sparse.result()

        # RRF 融合（使用自定义权重）
        results = retriever._merge(dense, sparse, dense_weight=req.vector_weight, sparse_weight=req.bm25_weight)

    # Rerank（如果启用）
    logger.info('检索配置: mode=%s, rerank=%s, reranker_type=%s', req.search_mode, req.rerank_enabled, req.reranker_type)
    if req.rerank_enabled and len(results) > req.top_k:
        # 检查当前加载的重排器类型是否匹配
        if not retriever._reranker or (hasattr(retriever._reranker, 'name') and retriever._reranker.name != req.reranker_type):
            retriever._load_reranker(reranker_type=req.reranker_type)
        if retriever._reranker:
            logger.info('使用重排算法: %s', retriever._reranker.name)
            results = retriever._smart_rerank(results, req.top_k, req.question)
    else:
        logger.info('跳过重排: enabled=%s, results=%d, top_k=%d', req.rerank_enabled, len(results), req.top_k)

    return results[:req.top_k]


def _format_sources(sources: list) -> list:
    return [{'chunk_id': r['chunk_id'], 'section_title': r.get('section_title', ''),
             'source_file': r.get('source_file', ''),
             'content': r['content'][:200]} for r in sources]


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

    # 读取多轮对话历史（从 Redis）
    history = session_mem.get_history(req.chat_id) if req.chat_id else []

    # 快速检索
    results = _search(comp, req)
    contexts = _build_context_from_results(results)
    answer = comp['generator'].generate(req.question, contexts, req.language, history=history)

    # 存储本轮对话到 Redis（供后续追问使用）
    if req.chat_id:
        session_mem.add(req.chat_id, 'user', req.question)
        session_mem.add(req.chat_id, 'assistant', answer)

    sources = _format_sources(results)
    qa = _quick_analysis(req.question)
    cache_set(cache_key, {'answer': answer, 'sources': sources, 'query_analysis': qa})
    return QueryResponse(answer=answer, sources=sources, query_analysis=qa)


@router.post('/query/compare', response_model=CompareResponse)
async def query_compare(req: QueryRequest):
    comp = get_components()
    start = time.time()

    results = _search(comp, req)
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

    # 读取多轮对话历史
    history = session_mem.get_history(req.chat_id) if req.chat_id else []

    if _is_greeting(req.question):
        async def greet_stream():
            yield f"data: {json.dumps({'type': 'token', 'data': '你好！有什么可以帮你的吗？'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(greet_stream(), media_type="text/event-stream")

    # 快速检索
    results = _search(comp, req)
    contexts = _build_context_from_results(results)

    sources = _format_sources(results)
    qa = _quick_analysis(req.question)

    async def generate():
        ai_answer = ""
        yield f"data: {json.dumps({'type': 'sources', 'data': sources}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'config', 'data': {'search_mode': req.search_mode, 'reranker_type': req.reranker_type, 'rerank_enabled': req.rerank_enabled, 'match_mode': req.match_mode, 'embedding_model': req.embedding_model or comp['embedder'].current_model}}, ensure_ascii=False)}\n\n"


        for token in comp["generator"].generate_stream(req.question, contexts, req.language, history=history):
            ai_answer += token
            yield f"data: {json.dumps({'type': 'token', 'data': token}, ensure_ascii=False)}\n\n"

        # 流式结束后，存储本轮对话到 Redis
        if req.chat_id:
            session_mem.add(req.chat_id, 'user', req.question)
            session_mem.add(req.chat_id, 'assistant', ai_answer)

        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")







