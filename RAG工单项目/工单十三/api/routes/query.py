"""问答路由（查询、流式、对比、分析）"""
from __future__ import annotations

import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api.cache import cache_get, cache_set, get_cache_key
from api.init import get_components
from api.models import (
    CompareResponse,
    QueryAnalysisResponse,
    QueryRequest,
    QueryResponse,
    RetrievalResponse,
)
from scripts.memory.session_memory import SessionMemory

logger = logging.getLogger(__name__)
router = APIRouter()

session_mem = SessionMemory()

_GREETING_PATTERNS = [
    "你好",
    "您好",
    "嗨",
    "哈哈",
    "hello",
    "hi",
    "hey",
    "谢谢",
    "感谢",
    "thanks",
    "thank you",
    "再见",
    "拜拜",
    "bye",
    "goodbye",
    "你是谁",
    "你是谁啊",
    "你叫什么",
    "你是什么",
    "能做什么",
    "你能做什么",
    "怎么用",
    "怎么使用",
    "早上好",
    "下午好",
    "晚上好",
    "晚安",
    "好的",
    "知道了",
    "明白",
    "ok",
    "okay",
]

_TIMING_KEYS = [
    "cache_lookup",
    "history_load",
    "embedding",
    "vector_search",
    "bm25_search",
    "merge",
    "rerank",
    "context_build",
    "llm_ttft",
    "llm_total",
    "total",
]

_CONTEXT_TOP_K = 3
_MAX_RERANK_CANDIDATES = 12


def _new_trace_id() -> str:
    return uuid.uuid4().hex


def _new_timings() -> Dict[str, float]:
    return {key: 0.0 for key in _TIMING_KEYS}


def _mark_timing(timings: Dict[str, float], key: str, start: float) -> float:
    value = round((time.perf_counter() - start) * 1000, 3)
    timings[key] = value
    return value


def _current_total_ms(start: float) -> int:
    return int(round((time.perf_counter() - start) * 1000))


def _cache_key_for_request(req: QueryRequest) -> str:
    question = (
        f"{req.question}|{req.search_mode}|{req.match_mode}|{req.rerank_enabled}|"
        f"{req.reranker_type}|{req.embedding_model or ''}|{req.vector_weight}|{req.bm25_weight}"
    )
    return get_cache_key(question, req.top_k, req.language)


def _is_greeting(question: str) -> bool:
    q = question.strip().lower().rstrip("。？！?.")
    return q in _GREETING_PATTERNS


def _quick_analysis(question: str) -> dict:
    q = question.strip().lower()
    if any(word in q for word in ["哪些", "列举", "几个", "list", "what are"]):
        intent, desc = "list", "list question"
    elif any(word in q for word in ["比较", "区别", "对比", "vs", "compare"]):
        intent, desc = "comparison", "comparison question"
    elif any(word in q for word in ["总结", "概括", "summarize"]):
        intent, desc = "summary", "summary question"
    elif any(word in q for word in ["为什么", "原因", "why", "how"]):
        intent, desc = "explanation", "explanation question"
    else:
        intent, desc = "factoid", "factoid question"

    return {
        "intent": intent,
        "intent_description": desc,
        "disambiguated_query": question,
        "sub_queries": [question],
        "keywords": [],
        "confidence": 0.8,
    }


def _format_sources(results: list) -> list:
    return [
        {
            "chunk_id": item["chunk_id"],
            "section_title": item.get("section_title", ""),
            "source_file": item.get("source_file", ""),
            "content": item["content"][:200],
        }
        for item in results
    ]


def _build_context_from_results(results: list, top_k: int = _CONTEXT_TOP_K) -> list:
    contexts = []
    for item in results[:top_k]:
        context = type(
            "Ctx",
            (),
            {
                "content": item["content"],
                "metadata": {
                    "section_title": item.get("section_title", ""),
                    "source_file": item.get("source_file", ""),
                },
            },
        )()
        contexts.append(context)
    return contexts


def _cacheable_payload(answer: str, sources: list, query_analysis: dict) -> dict:
    return {
        "answer": answer,
        "sources": sources,
        "query_analysis": query_analysis,
    }


def _response_payload(
    *,
    answer: str,
    sources: list,
    query_analysis: dict,
    trace_id: str,
    timings: Dict[str, float],
    retrieval_time_ms: int,
    total_time_ms: int,
    cache_hit: bool,
) -> dict:
    return {
        "answer": answer,
        "sources": sources,
        "query_analysis": query_analysis,
        "trace_id": trace_id,
        "timings": timings,
        "retrieval_time_ms": retrieval_time_ms,
        "total_time_ms": total_time_ms,
        "cache_hit": cache_hit,
    }


def _retrieval_payload(
    *,
    sources: list,
    query_analysis: dict,
    trace_id: str,
    timings: Dict[str, float],
    retrieval_time_ms: int,
    total_time_ms: int,
    cache_hit: bool,
) -> dict:
    return {
        "sources": sources,
        "query_analysis": query_analysis,
        "trace_id": trace_id,
        "timings": timings,
        "retrieval_time_ms": retrieval_time_ms,
        "total_time_ms": total_time_ms,
        "cache_hit": cache_hit,
    }


def _done_event_payload(
    trace_id: str,
    timings: Dict[str, float],
    retrieval_time_ms: int,
    total_time_ms: int,
    cache_hit: bool,
) -> dict:
    return {
        "trace_id": trace_id,
        "timings": timings,
        "retrieval_time_ms": retrieval_time_ms,
        "total_time_ms": total_time_ms,
        "cache_hit": cache_hit,
    }


def _log_trace(
    *,
    endpoint: str,
    trace_id: str,
    req: QueryRequest,
    timings: Dict[str, float],
    retrieval_time_ms: int,
    total_time_ms: int,
    cache_hit: bool,
    source_count: int,
    context_chars: int = 0,
) -> None:
    logger.info(
        json.dumps(
            {
                "trace_id": trace_id,
                "endpoint": endpoint,
                "question": req.question,
                "top_k": req.top_k,
                "search_mode": req.search_mode,
                "match_mode": req.match_mode,
                "reranker_type": req.reranker_type,
                "cache_hit": cache_hit,
                "source_count": source_count,
                "context_chars": context_chars,
                "retrieval_time_ms": retrieval_time_ms,
                "total_time_ms": total_time_ms,
                "timings": timings,
            },
            ensure_ascii=False,
        )
    )


def _search(comp: dict, req: QueryRequest, timings: Dict[str, float]) -> list:
    retriever = comp["retriever"]
    embedder = comp["embedder"]

    if req.embedding_model and hasattr(embedder, "switch_model"):
        embedder.switch_model(req.embedding_model)

    if req.search_mode == "vector":
        stage_start = time.perf_counter()
        query_vec = embedder.encode([req.question])[0]
        _mark_timing(timings, "embedding", stage_start)

        stage_start = time.perf_counter()
        results = retriever._vs.search(query_vec, req.top_k * 3)
        _mark_timing(timings, "vector_search", stage_start)

    elif req.search_mode == "bm25":
        stage_start = time.perf_counter()
        results = retriever._bm25.search(req.question, req.top_k * 4, match_mode=req.match_mode)
        _mark_timing(timings, "bm25_search", stage_start)

    else:
        bm25_meta: Dict[str, float] = {}

        def run_sparse():
            sparse_start = time.perf_counter()
            sparse_results = retriever._bm25.search(req.question, req.top_k * 4, match_mode=req.match_mode)
            bm25_meta["duration"] = round((time.perf_counter() - sparse_start) * 1000, 3)
            return sparse_results

        with ThreadPoolExecutor(max_workers=2) as executor:
            sparse_future = executor.submit(run_sparse)

            stage_start = time.perf_counter()
            query_vec = embedder.encode([req.question])[0]
            _mark_timing(timings, "embedding", stage_start)

            stage_start = time.perf_counter()
            dense = retriever._vs.search(query_vec, req.top_k * 3)
            _mark_timing(timings, "vector_search", stage_start)

            sparse = sparse_future.result()

        timings["bm25_search"] = bm25_meta.get("duration", 0.0)

        stage_start = time.perf_counter()
        results = retriever._merge(
            dense,
            sparse,
            dense_weight=req.vector_weight,
            sparse_weight=req.bm25_weight,
        )
        _mark_timing(timings, "merge", stage_start)

    logger.info(
        "检索配置: mode=%s, rerank=%s, reranker_type=%s",
        req.search_mode,
        req.rerank_enabled,
        req.reranker_type,
    )

    if req.rerank_enabled and len(results) > req.top_k:
        stage_start = time.perf_counter()
        if not retriever._reranker or (
            hasattr(retriever._reranker, "name") and retriever._reranker.name != req.reranker_type
        ):
            retriever._load_reranker(reranker_type=req.reranker_type)
        if retriever._reranker:
            candidates = results[: max(req.top_k, _MAX_RERANK_CANDIDATES)]
            results = retriever._smart_rerank(candidates, req.top_k, req.question)
        _mark_timing(timings, "rerank", stage_start)
    else:
        logger.info("跳过重排: enabled=%s, results=%d, top_k=%d", req.rerank_enabled, len(results), req.top_k)

    return results[: req.top_k]


@router.post("/query/analyze", response_model=QueryAnalysisResponse)
async def analyze_query(req: QueryRequest):
    comp = get_components()
    analysis = comp["query_understanding"].analyze(req.question)
    return QueryAnalysisResponse(
        original_query=analysis.original_query,
        intent=analysis.intent,
        intent_description=analysis.intent_description,
        disambiguated_query=analysis.disambiguated_query,
        sub_queries=analysis.sub_queries,
        keywords=analysis.keywords,
        confidence=analysis.confidence,
    )


@router.post("/query/retrieve", response_model=RetrievalResponse)
async def retrieve(req: QueryRequest):
    trace_id = _new_trace_id()
    timings = _new_timings()
    total_start = time.perf_counter()

    cache_start = time.perf_counter()
    timings["cache_lookup"] = round((time.perf_counter() - cache_start) * 1000, 3)

    retrieval_start = time.perf_counter()
    comp = get_components()
    results = _search(comp, req, timings)
    retrieval_time_ms = int(round((time.perf_counter() - retrieval_start) * 1000))
    sources = _format_sources(results)
    payload = _retrieval_payload(
        sources=sources,
        query_analysis=_quick_analysis(req.question),
        trace_id=trace_id,
        timings=timings,
        retrieval_time_ms=retrieval_time_ms,
        total_time_ms=0,
        cache_hit=False,
    )
    payload["total_time_ms"] = _current_total_ms(total_start)
    timings["total"] = float(payload["total_time_ms"])
    _log_trace(
        endpoint="retrieve",
        trace_id=trace_id,
        req=req,
        timings=timings,
        retrieval_time_ms=retrieval_time_ms,
        total_time_ms=payload["total_time_ms"],
        cache_hit=False,
        source_count=len(sources),
    )
    return RetrievalResponse(**payload)


@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    trace_id = _new_trace_id()
    timings = _new_timings()
    total_start = time.perf_counter()
    cache_key = _cache_key_for_request(req)

    cache_start = time.perf_counter()
    cached = cache_get(cache_key)
    _mark_timing(timings, "cache_lookup", cache_start)
    if cached:
        total_time_ms = _current_total_ms(total_start)
        timings["total"] = float(total_time_ms)
        payload = _response_payload(
            answer=cached["answer"],
            sources=cached["sources"],
            query_analysis=cached["query_analysis"],
            trace_id=trace_id,
            timings=timings,
            retrieval_time_ms=0,
            total_time_ms=total_time_ms,
            cache_hit=True,
        )
        _log_trace(
            endpoint="query",
            trace_id=trace_id,
            req=req,
            timings=timings,
            retrieval_time_ms=0,
            total_time_ms=total_time_ms,
            cache_hit=True,
            source_count=len(cached["sources"]),
        )
        return QueryResponse(**payload)

    if _is_greeting(req.question):
        total_time_ms = _current_total_ms(total_start)
        timings["total"] = float(total_time_ms)
        payload = _response_payload(
            answer="你好！有什么可以帮你的吗？",
            sources=[],
            query_analysis=_quick_analysis(req.question),
            trace_id=trace_id,
            timings=timings,
            retrieval_time_ms=0,
            total_time_ms=total_time_ms,
            cache_hit=False,
        )
        _log_trace(
            endpoint="query",
            trace_id=trace_id,
            req=req,
            timings=timings,
            retrieval_time_ms=0,
            total_time_ms=total_time_ms,
            cache_hit=False,
            source_count=0,
        )
        return QueryResponse(**payload)

    comp = get_components()

    history = []
    if req.chat_id:
        history_start = time.perf_counter()
        history = session_mem.get_history(req.chat_id)
        _mark_timing(timings, "history_load", history_start)

    retrieval_start = time.perf_counter()
    results = _search(comp, req, timings)

    context_start = time.perf_counter()
    contexts = _build_context_from_results(results)
    context_chars = sum(len(ctx.content) for ctx in contexts)
    _mark_timing(timings, "context_build", context_start)
    retrieval_time_ms = int(round((time.perf_counter() - retrieval_start) * 1000))

    llm_start = time.perf_counter()
    answer = comp["generator"].generate(req.question, contexts, req.language, history=history)
    llm_total = _mark_timing(timings, "llm_total", llm_start)
    timings["llm_ttft"] = llm_total

    if req.chat_id:
        session_mem.add(req.chat_id, "user", req.question)
        session_mem.add(req.chat_id, "assistant", answer)

    sources = _format_sources(results)
    query_analysis = _quick_analysis(req.question)
    cache_set(cache_key, _cacheable_payload(answer, sources, query_analysis))

    total_time_ms = _current_total_ms(total_start)
    timings["total"] = float(total_time_ms)
    payload = _response_payload(
        answer=answer,
        sources=sources,
        query_analysis=query_analysis,
        trace_id=trace_id,
        timings=timings,
        retrieval_time_ms=retrieval_time_ms,
        total_time_ms=total_time_ms,
        cache_hit=False,
    )
    _log_trace(
        endpoint="query",
        trace_id=trace_id,
        req=req,
        timings=timings,
        retrieval_time_ms=retrieval_time_ms,
        total_time_ms=total_time_ms,
        cache_hit=False,
        source_count=len(sources),
        context_chars=context_chars,
    )
    return QueryResponse(**payload)


@router.post("/query/compare", response_model=CompareResponse)
async def query_compare(req: QueryRequest):
    trace_id = _new_trace_id()
    timings = _new_timings()
    total_start = time.perf_counter()
    comp = get_components()

    retrieval_start = time.perf_counter()
    results = _search(comp, req, timings)
    context_start = time.perf_counter()
    contexts = _build_context_from_results(results)
    _mark_timing(timings, "context_build", context_start)
    retrieval_time_ms = int(round((time.perf_counter() - retrieval_start) * 1000))

    llm_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=2) as executor:
        rag_future = executor.submit(comp["generator"].generate, req.question, contexts, req.language)
        llm_future = executor.submit(comp["generator"].generate, req.question, [], req.language)
        rag_answer = rag_future.result()
        llm_answer = llm_future.result()
    llm_total = _mark_timing(timings, "llm_total", llm_start)
    timings["llm_ttft"] = llm_total

    total_time_ms = _current_total_ms(total_start)
    timings["total"] = float(total_time_ms)

    payload = {
        "rag_answer": rag_answer,
        "rag_sources": _format_sources(results),
        "llm_answer": llm_answer,
        "response_time_ms": total_time_ms,
        "trace_id": trace_id,
        "timings": timings,
        "retrieval_time_ms": retrieval_time_ms,
        "total_time_ms": total_time_ms,
        "cache_hit": False,
    }
    _log_trace(
        endpoint="compare",
        trace_id=trace_id,
        req=req,
        timings=timings,
        retrieval_time_ms=retrieval_time_ms,
        total_time_ms=total_time_ms,
        cache_hit=False,
        source_count=len(payload["rag_sources"]),
    )
    return CompareResponse(**payload)


@router.post("/query/stream")
async def query_stream(req: QueryRequest):
    trace_id = _new_trace_id()
    timings = _new_timings()
    total_start = time.perf_counter()
    cache_key = _cache_key_for_request(req)

    cache_start = time.perf_counter()
    cached = cache_get(cache_key)
    _mark_timing(timings, "cache_lookup", cache_start)

    if _is_greeting(req.question):
        async def greet_stream():
            total_time_ms = _current_total_ms(total_start)
            timings["total"] = float(total_time_ms)
            yield f"data: {json.dumps({'type': 'token', 'data': '你好！有什么可以帮你的吗？'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'data': _done_event_payload(trace_id, timings, 0, total_time_ms, False)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(greet_stream(), media_type="text/event-stream")

    if cached:
        async def cached_stream():
            total_time_ms = _current_total_ms(total_start)
            timings["total"] = float(total_time_ms)
            yield f"data: {json.dumps({'type': 'sources', 'data': cached['sources']}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'query_analysis', 'data': cached['query_analysis']}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'config', 'data': {'search_mode': req.search_mode, 'reranker_type': req.reranker_type, 'rerank_enabled': req.rerank_enabled, 'match_mode': req.match_mode, 'embedding_model': req.embedding_model or ''}}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'token', 'data': cached['answer']}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'data': _done_event_payload(trace_id, timings, 0, total_time_ms, True)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(cached_stream(), media_type="text/event-stream")

    comp = get_components()
    history = []
    if req.chat_id:
        history_start = time.perf_counter()
        history = session_mem.get_history(req.chat_id)
        _mark_timing(timings, "history_load", history_start)

    retrieval_start = time.perf_counter()
    results = _search(comp, req, timings)
    sources = _format_sources(results)
    query_analysis = _quick_analysis(req.question)

    context_start = time.perf_counter()
    contexts = _build_context_from_results(results)
    context_chars = sum(len(ctx.content) for ctx in contexts)
    _mark_timing(timings, "context_build", context_start)
    retrieval_time_ms = int(round((time.perf_counter() - retrieval_start) * 1000))

    async def generate():
        answer_parts = []
        llm_start = time.perf_counter()
        first_token_seen = False

        yield f"data: {json.dumps({'type': 'sources', 'data': sources}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'query_analysis', 'data': query_analysis}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'config', 'data': {'search_mode': req.search_mode, 'reranker_type': req.reranker_type, 'rerank_enabled': req.rerank_enabled, 'match_mode': req.match_mode, 'embedding_model': req.embedding_model or comp['embedder'].current_model}}, ensure_ascii=False)}\n\n"

        for token in comp["generator"].generate_stream(req.question, contexts, req.language, history=history):
            if not first_token_seen:
                first_token_seen = True
                _mark_timing(timings, "llm_ttft", llm_start)
            answer_parts.append(token)
            yield f"data: {json.dumps({'type': 'token', 'data': token}, ensure_ascii=False)}\n\n"

        answer = "".join(answer_parts)
        if not first_token_seen:
            timings["llm_ttft"] = 0.0
        _mark_timing(timings, "llm_total", llm_start)

        if req.chat_id:
            session_mem.add(req.chat_id, "user", req.question)
            session_mem.add(req.chat_id, "assistant", answer)

        cache_set(cache_key, _cacheable_payload(answer, sources, query_analysis))

        total_time_ms = _current_total_ms(total_start)
        timings["total"] = float(total_time_ms)
        _log_trace(
            endpoint="stream",
            trace_id=trace_id,
            req=req,
            timings=timings,
            retrieval_time_ms=retrieval_time_ms,
            total_time_ms=total_time_ms,
            cache_hit=False,
            source_count=len(sources),
            context_chars=context_chars,
        )
        yield f"data: {json.dumps({'type': 'done', 'data': _done_event_payload(trace_id, timings, retrieval_time_ms, total_time_ms, False)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
