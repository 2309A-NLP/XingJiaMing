"""LightRAG 知识图谱服务

基于 HKUDS/LightRAG，使用 Neo4j 存储知识图谱，
与传统RAG（向量+BM25）形成对比。
"""
from __future__ import annotations
import asyncio
import logging
import os
import threading
from pathlib import Path
from typing import Optional

# 绕过代理，确保LLM API直连
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ['no_proxy'] = '*'
os.environ['NO_PROXY'] = '*'

logger = logging.getLogger(__name__)

# 全局单例
_lightrag_instance = None
_lightrag_lock = threading.Lock()
_lightrag_initialized = False


def _get_lightrag():
    """懒加载 LightRAG 实例（线程安全单例）"""
    global _lightrag_instance
    if _lightrag_instance is not None:
        return _lightrag_instance

    with _lightrag_lock:
        if _lightrag_instance is not None:
            return _lightrag_instance

        from lightrag import LightRAG
        from lightrag.utils import EmbeddingFunc
        from dotenv import load_dotenv

        load_dotenv(override=True)

        # 配置
        working_dir = os.getenv('LIGHTRAG_WORKING_DIR', './lightrag_storage')
        os.makedirs(working_dir, exist_ok=True)

        # LLM 配置 - 使用 DeepSeek
        api_key = os.getenv('MIMO_API_KEY', '')
        base_url = os.getenv('MIMO_BASE_URL', 'https://api.deepseek.com/v1')
        llm_model = os.getenv('MIMO_MODEL', 'deepseek-chat')

        # Embedding 配置 - 复用 BGE-M3
        embedding_model_path = os.getenv('EMBEDDING_MODEL_PATH', '')

        # Neo4j 配置
        neo4j_uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
        neo4j_user = os.getenv('NEO4J_USERNAME', 'neo4j')
        neo4j_pass = os.getenv('NEO4J_PASSWORD', 'neo4j123')

        # 设置 Neo4j 环境变量（LightRAG 内部读取）
        os.environ['NEO4J_URI'] = neo4j_uri
        os.environ['NEO4J_USERNAME'] = neo4j_user
        os.environ['NEO4J_PASSWORD'] = neo4j_pass

        logger.info('初始化 LightRAG...')
        logger.info('  LLM: %s @ %s', llm_model, base_url)
        logger.info('  Embedding: %s', embedding_model_path)
        logger.info('  Neo4j: %s', neo4j_uri)
        logger.info('  WorkingDir: %s', working_dir)

        # LLM 函数封装（必须是async）
        async def llm_func(prompt: str, system_prompt: str = None, **kwargs) -> str:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=120.0, max_retries=3)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            resp = await client.chat.completions.create(
                model=llm_model,
                messages=messages,
                temperature=0.1,
            )
            return resp.choices[0].message.content

        # Embedding 函数封装（必须是async）
        _embedder_cache = {}

        # 转换Windows路径到WSL路径
        def _to_wsl_path(win_path: str) -> str:
            if win_path and len(win_path) >= 2 and win_path[1] == ':':
                drive = win_path[0].lower()
                rest = win_path[2:].replace('\\', '/')
                return f'/mnt/{drive}{rest}'
            return win_path

        async def embedding_func(texts: list[str]) -> list[list[float]]:
            cache_key = embedding_model_path
            if cache_key not in _embedder_cache:
                from sentence_transformers import SentenceTransformer
                # 强制CPU，避免GPU显存不足
                wsl_path = _to_wsl_path(embedding_model_path)
                _embedder_cache[cache_key] = SentenceTransformer(
                    wsl_path, device='cuda'
                )
                logger.info('LightRAG Embedding 模型加载完成(GPU): %s', wsl_path)
            model = _embedder_cache[cache_key]
            vectors = model.encode(texts, normalize_embeddings=True, batch_size=16)
            return vectors

        # Rerank 模型路径
        rerank_path = os.getenv('RERANK_MODEL_PATH', '')

        # Rerank 函数封装（复用 BGE-Reranker）
        _reranker_cache = {}

        async def rerank_func(query: str, documents: list[str], top_n: int = None):
            """LightRAG rerank 回调：用 BGE-Reranker 对检索结果重排序"""
            if not documents:
                return []
            cache_key = rerank_path
            if cache_key not in _reranker_cache:
                from sentence_transformers import CrossEncoder
                wsl_rerank_path = _to_wsl_path(rerank_path) if rerank_path else rerank_path
                _reranker_cache[cache_key] = CrossEncoder(wsl_rerank_path, device='cuda')
                logger.info('LightRAG Reranker 模型加载完成(GPU): %s', wsl_rerank_path)
            model = _reranker_cache[cache_key]
            pairs = [[query, doc] for doc in documents]
            scores = model.predict(pairs)
            results = [{"index": i, "relevance_score": float(s)} for i, s in enumerate(scores)]
            results.sort(key=lambda x: x["relevance_score"], reverse=True)
            if top_n:
                results = results[:top_n]
            return results

        # 创建 LightRAG 实例
        _lightrag_instance = LightRAG(
            working_dir=working_dir,
            llm_model_func=llm_func,
            embedding_func=EmbeddingFunc(
                embedding_dim=1024,  # BGE-M3 输出维度
                max_token_size=512,
                func=embedding_func,
            ),
            rerank_model_func=rerank_func if rerank_path else None,
            # graph_storage="Neo4JStorage",  # Neo4j为空，使用默认NetworkX
            chunk_token_size=1200,
            chunk_overlap_token_size=100,
        )

        logger.info('LightRAG 实例创建完成')
        return _lightrag_instance


async def _ensure_initialized():
    """确保 LightRAG 存储已初始化（异步，只调一次）"""
    global _lightrag_initialized
    if _lightrag_initialized:
        return
    rag = _get_lightrag()
    await rag.initialize_storages()
    _lightrag_initialized = True
    logger.info('LightRAG 存储初始化完成')


def insert_documents(texts: list[str], file_paths: list[str] = None) -> str:
    """同步插入文档到 LightRAG 知识图谱"""
    rag = _get_lightrag()
    return rag.insert(input=texts, file_paths=file_paths)


async def ainsert_documents(texts: list[str], file_paths: list[str] = None) -> str:
    """异步插入文档到 LightRAG 知识图谱"""
    await _ensure_initialized()
    rag = _get_lightrag()
    return await rag.ainsert(input=texts, file_paths=file_paths)


def query_lightrag(question: str, mode: str = "hybrid") -> str:
    """同步查询 LightRAG
    
    Args:
        question: 查询问题
        mode: 查询模式 - "local"(局部), "global"(全局), "hybrid"(混合), "naive"(纯文本)
    """
    from lightrag.base import QueryParam
    rag = _get_lightrag()
    param = QueryParam(
        mode=mode,
        top_k=5,
        chunk_top_k=3,
        enable_rerank=False,
    )
    return rag.query(query=question, param=param)


async def aquery_lightrag(question: str, mode: str = "hybrid") -> str:
    """异步查询 LightRAG"""
    await _ensure_initialized()
    from lightrag.base import QueryParam
    rag = _get_lightrag()
    param = QueryParam(
        mode=mode,
        top_k=5,
        chunk_top_k=3,
        enable_rerank=False,
    )
    return await rag.aquery(query=question, param=param)


def get_status() -> dict:
    """获取 LightRAG 状态"""
    try:
        rag = _get_lightrag()
        working_dir = rag.working_dir
        # 检查存储目录是否有数据
        storage_path = Path(working_dir)
        has_data = any(storage_path.glob("*.json")) if storage_path.exists() else False
        return {
            "status": "ready" if has_data else "empty",
            "working_dir": str(working_dir),
            "has_knowledge_graph": has_data,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _format_lightrag_context(data: dict) -> str:
    """将 LightRAG aquery_data 的结构化结果格式化为 LLM 上下文"""
    if not data or data.get("status") != "success":
        return ""

    entities = data.get("data", {}).get("entities", [])
    relationships = data.get("data", {}).get("relationships", [])
    chunks = data.get("data", {}).get("chunks", [])

    parts = []

    if entities:
        parts.append("## 知识图谱实体")
        for e in entities[:15]:
            name = e.get("entity_name", "")
            desc = e.get("description", "")[:200]
            parts.append(f"- **{name}**: {desc}")

    if relationships:
        parts.append("\n## 知识图谱关系")
        for r in relationships[:15]:
            src = r.get("src_id", "")
            tgt = r.get("tgt_id", "")
            desc = r.get("description", "")[:200]
            parts.append(f"- **{src}** → **{tgt}**: {desc}")

    if chunks:
        parts.append("\n## 相关文档片段")
        for c in chunks[:5]:
            content = c.get("content", "")[:300]
            parts.append(f"- {content}")

    return "\n".join(parts)


async def aquery_lightrag_stream(question: str, mode: str = "hybrid"):
    """LightRAG 流式查询：先检索图谱，再用 LLM 流式生成回答"""
    import json
    from openai import AsyncOpenAI
    from lightrag.base import QueryParam

    await _ensure_initialized()
    rag = _get_lightrag()

    # 第一步：用 aquery_data 检索图谱上下文
    param = QueryParam(mode=mode, top_k=5, chunk_top_k=3, enable_rerank=False)
    data_result = await rag.aquery_data(query=question, param=param)

    context = _format_lightrag_context(data_result)
    if not context:
        yield "LightRAG 知识图谱中未找到相关信息。"
        return

    # 第二步：用 DeepSeek 流式生成回答
    api_key = os.getenv('MIMO_API_KEY', '')
    base_url = os.getenv('MIMO_BASE_URL', 'https://api.deepseek.com/v1')
    llm_model = os.getenv('MIMO_MODEL', 'deepseek-chat')

    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=120.0, max_retries=3)

    system_prompt = """你是一个专业的文档问答助手。基于以下知识图谱检索结果回答用户问题。
要求：
- 回答准确、简洁
- 如果图表数据中包含具体数值，必须完整列出
- 不要编造信息，只基于提供的上下文回答"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"## 检索上下文\n\n{context}\n\n## 用户问题\n\n{question}"},
    ]

    try:
        stream = await client.chat.completions.create(
            model=llm_model,
            messages=messages,
            temperature=0.1,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
    except Exception as e:
        logger.error('LightRAG 流式生成失败: %s', e)
        yield f"\n\n[生成失败: {str(e)[:100]}]"
