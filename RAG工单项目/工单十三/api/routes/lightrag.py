"""LightRAG API 路由

提供知识图谱构建和 LightRAG 检索接口。
"""
from __future__ import annotations
import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lightrag", tags=["lightrag"])


class InsertRequest(BaseModel):
    """文档插入请求"""
    file_patterns: list[str] = Field(
        default=["*_refined.md"],
        description="data/ 目录下要处理的文件匹配模式"
    )


class QueryRequest(BaseModel):
    """LightRAG 查询请求"""
    question: str = Field(..., description="查询问题")
    mode: str = Field(default="hybrid", description="查询模式: local/global/hybrid/naive")


class CompareRequest(BaseModel):
    """RAG vs LightRAG 对比请求"""
    question: str = Field(..., description="查询问题")


# ── 知识图谱构建 ──

@router.post("/insert")
async def insert_documents(req: InsertRequest):
    """将 data/ 下的文档插入 LightRAG 知识图谱"""
    from scripts.pipeline.lightrag_service import ainsert_documents

    data_dir = Path(os.getenv('DATA_DIR', './data'))
    texts = []
    file_paths = []

    for pattern in req.file_patterns:
        for f in sorted(data_dir.glob(pattern)):
            content = f.read_text(encoding='utf-8')
            texts.append(content)
            file_paths.append(str(f))
            logger.info('加载文档: %s (%d 字符)', f.name, len(content))

    if not texts:
        raise HTTPException(400, f"data/ 下未找到匹配 {req.file_patterns} 的文件")

    try:
        track_id = await ainsert_documents(texts=texts, file_paths=file_paths)
        return {
            "status": "success",
            "track_id": track_id,
            "documents": len(texts),
            "files": [Path(p).name for p in file_paths],
        }
    except Exception as e:
        logger.error('LightRAG 插入失败: %s', e, exc_info=True)
        raise HTTPException(500, f"插入失败: {e}")


# ── LightRAG 检索 ──

@router.post("/query")
async def query_lightrag(req: QueryRequest):
    """使用 LightRAG 检索"""
    from scripts.pipeline.lightrag_service import aquery_lightrag

    try:
        answer = await aquery_lightrag(question=req.question, mode=req.mode)
        return {
            "answer": answer,
            "mode": req.mode,
            "source": "lightrag",
        }
    except Exception as e:
        logger.error('LightRAG 查询失败: %s', e, exc_info=True)
        raise HTTPException(500, f"查询失败: {e}")


# ── RAG vs LightRAG 对比 ──

_compare_cache: dict = {}

@router.post("/compare")
async def compare_rag_lightrag(req: CompareRequest):
    """并行用传统RAG和LightRAG检索，返回对比结果（带缓存）"""
    from scripts.pipeline.lightrag_service import aquery_lightrag
    from api.init import get_components
    import time

    # 缓存检查
    cache_key = req.question.strip()
    if cache_key in _compare_cache:
        logger.info('对比缓存命中: %s', cache_key[:30])
        return _compare_cache[cache_key]

    import asyncio
    import concurrent.futures

    async def _run_lightrag():
        """LightRAG查询"""
        start = time.time()
        try:
            answer = await aquery_lightrag(question=req.question, mode="hybrid")
            return {
                "answer": answer,
                "error": None,
                "time_ms": int((time.time() - start) * 1000),
            }
        except Exception as e:
            logger.warning('LightRAG 检索失败: %s', e)
            return {
                "answer": "",
                "error": str(e),
                "time_ms": int((time.time() - start) * 1000),
            }

    async def _run_rag():
        """传统RAG查询"""
        start = time.time()
        try:
            components = get_components()
            retriever = components['retriever']
            generator = components['generator']
            embedder = components['embedder']

            # 编码 + 检索
            query_vec = embedder.encode([req.question])[0]
            results = retriever._vs.search(query_vec, 10)

            # 构建上下文
            contexts = []
            sources = []
            for r in results:
                ctx = type('Ctx', (), {
                    'content': r['content'],
                    'metadata': {
                        'section_title': r.get('section_title', ''),
                        'source_file': r.get('source_file', ''),
                    }
                })()
                contexts.append(ctx)
                sources.append({
                    'section_title': r.get('section_title', ''),
                    'source_file': r.get('source_file', ''),
                    'content': r['content'][:150],
                })

            answer = generator.generate(req.question, contexts, 'zh')
            return {
                "answer": answer,
                "error": None,
                "sources": sources,
                "time_ms": int((time.time() - start) * 1000),
            }
        except Exception as e:
            logger.warning('传统RAG 检索失败: %s', e)
            return {
                "answer": "",
                "error": str(e),
                "sources": [],
                "time_ms": int((time.time() - start) * 1000),
            }

    # 并行执行
    total_start = time.time()
    lightrag_result, rag_result = await asyncio.gather(
        _run_lightrag(),
        _run_rag(),
    )
    total_ms = int((time.time() - total_start) * 1000)

    result = {
        "question": req.question,
        "lightrag": lightrag_result,
        "traditional_rag": rag_result,
        "total_time_ms": total_ms,
    }

    # 缓存结果
    _compare_cache[cache_key] = result

    return result


# ── 状态查询 ──

@router.get("/status")
async def get_status():
    """获取 LightRAG 状态"""
    from scripts.pipeline.lightrag_service import get_status
    return get_status()


# ── LightRAG 流式查询 ──

@router.post("/stream")
async def query_lightrag_stream(req: QueryRequest):
    """LightRAG 流式查询（SSE）：先检索图谱，再流式生成"""
    import json as _json
    from fastapi.responses import StreamingResponse
    from scripts.pipeline.lightrag_service import aquery_lightrag_stream

    async def event_generator():
        try:
            async for token in aquery_lightrag_stream(question=req.question, mode=req.mode):
                yield f"data: {_json.dumps({'type': 'token', 'data': token}, ensure_ascii=False)}\n\n"
            yield f"data: {_json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error('LightRAG 流式查询失败: %s', e, exc_info=True)
            yield f"data: {_json.dumps({'type': 'error', 'data': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── 准确率对比分析 ──

class AccuracyCompareRequest(BaseModel):
    question: str
    rag_answer: str
    lightrag_answer: str

@router.post("/accuracy-compare")
async def accuracy_compare(req: AccuracyCompareRequest):
    """用 LLM 分析两个回答的准确率"""
    import os
    from openai import AsyncOpenAI

    api_key = os.getenv('MIMO_API_KEY', '')
    base_url = os.getenv('MIMO_BASE_URL', 'https://api.deepseek.com/v1')
    llm_model = os.getenv('MIMO_MODEL', 'deepseek-chat')

    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=60.0)

    prompt = f"""请对比以下两个RAG系统对同一问题的回答，分析各自的准确性和质量。

## 用户问题
{req.question}

## 传统RAG的回答
{req.rag_answer}

## LightRAG（知识图谱）的回答
{req.lightrag_answer}

请从以下维度分析：
1. **事实准确性**：哪个回答的事实更准确？
2. **完整性**：哪个回答覆盖了更多关键信息？
3. **信息来源**：各自信检索方式的优势
4. **综合评分**：传统RAG vs LightRAG（满分10分）

用简洁的表格和要点总结。"""

    try:
        resp = await client.chat.completions.create(
            model=llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        analysis = resp.choices[0].message.content or "分析失败"
        return {"analysis": analysis}
    except Exception as e:
        logger.error('准确率对比失败: %s', e)
        return {"analysis": f"对比分析失败: {str(e)[:100]}"}


# ── 混合回答融合 ──

class MergeRequest(BaseModel):
    question: str
    rag_answer: str
    lightrag_answer: str

@router.post("/merge")
async def merge_answers(req: MergeRequest):
    """融合传统RAG和LightRAG的回答，生成更优的混合答案"""
    import json as _json
    from fastapi.responses import StreamingResponse
    from openai import AsyncOpenAI

    api_key = os.getenv('MIMO_API_KEY', '')
    base_url = os.getenv('MIMO_BASE_URL', 'https://api.deepseek.com/v1')
    llm_model = os.getenv('MIMO_MODEL', 'deepseek-chat')
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=60.0, max_retries=3)

    prompt = f"""你是一个专业的文档问答助手。请融合以下两个RAG系统的回答，生成一个更完整、更准确的最终答案。

## 用户问题
{req.question}

## 传统RAG的回答（基于向量检索，精确但可能不全面）
{req.rag_answer}

## LightRAG的回答（基于知识图谱推理，全面但可能有误差）
{req.lightrag_answer}

## 要求
1. 以传统RAG的精确数据为基础
2. 补充LightRAG中传统RAG遗漏的有价值信息
3. 如果两个回答有矛盾，以传统RAG的原始数据为准
4. 不要提及"传统RAG"或"LightRAG"，直接给出最终答案
5. 保持简洁，不超过300字"""

    async def event_generator():
        try:
            stream = await client.chat.completions.create(
                model=llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield f"data: {_json.dumps({'type': 'token', 'data': delta.content}, ensure_ascii=False)}\n\n"
            yield f"data: {_json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error('融合生成失败: %s', e)
            yield f"data: {_json.dumps({'type': 'token', 'data': req.rag_answer}, ensure_ascii=False)}\n\n"
            yield f"data: {_json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
