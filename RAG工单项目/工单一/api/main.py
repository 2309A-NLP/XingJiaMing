"""工单1 - RAG问答系统 API

工单编号：人工智能 NLP-RAG-基于 PDF 文档的问答系统

功能：
- Query 理解（意图识别、消歧、分解与抽象）
- 向量检索 + BM25 双路召回
- LLM 生成回答
- 对话管理
"""
from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, UploadFile, File, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from scripts.memory.chat_store import ChatStore
from scripts.memory.session_memory import SessionMemory
import json as _json

chat_store = ChatStore(db_path=os.path.join(os.path.dirname(__file__), '..', 'storage', 'chats.db'))
session_mem = SessionMemory()

load_dotenv(override=True)
logger = logging.getLogger(__name__)

app = FastAPI(title='RAG 智能问答系统 - 工单1', version='1.0.0')

# 创建路由器，所有接口都在 /api 下
router = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger.info('%s %s', request.method, request.url.path)
        response = await call_next(request)
        if response.status_code >= 400:
            logger.warning('%s %s -> %d', request.method, request.url.path, response.status_code)
        return response


app.add_middleware(LoggingMiddleware)


@app.on_event('startup')
async def on_startup():
    from scripts.logger import setup_logging
    setup_logging()
    logger.info('日志系统启动')


_components = {}


def _init():
    """初始化组件（懒加载）"""
    if _components:
        return _components
    from scripts.pipeline.chunker import Chunker
    from scripts.pipeline.embedder import Embedder
    from scripts.pipeline.vector_store import VectorStore
    from scripts.pipeline.bm25_retriever import BM25Retriever
    from scripts.pipeline.retriever import Retriever
    from scripts.pipeline.generator import Generator
    from scripts.pipeline.query_understanding import QueryUnderstanding

    logger.info('开始初始化...')

    # 从环境变量读取配置
    embedding_path = os.getenv('EMBEDDING_MODEL_PATH', r'E:\AI_models\BGE-M3')
    milvus_host = os.getenv('MILVUS_HOST', 'localhost')
    milvus_port = os.getenv('MILVUS_PORT', '19530')
    collection = os.getenv('MILVUS_COLLECTION', 'rag_workorder1')
    data_dir = Path(os.getenv('DATA_DIR', './data'))

    embedder = Embedder(model_path=embedding_path)
    store = VectorStore(host=milvus_host, port=milvus_port, collection=collection)

    # Rerank 可选
    reranker = None
    if os.getenv('RERANK_ENABLED', 'false').lower() == 'true':
        from scripts.pipeline.reranker import Reranker
        rerank_path = os.getenv('RERANK_MODEL_PATH', r'E:\AI_models\bge-reranker-base')
        reranker = Reranker(model_path=rerank_path)

    generator = Generator()
    query_understanding = QueryUnderstanding()

    # 加载已解析的markdown
    md_path = data_dir / '招股说明书1_refined.md'
    parents, children = [], []
    bm25 = BM25Retriever([])

    if md_path.exists():
        md = md_path.read_text(encoding='utf-8')
        parents, children = Chunker().chunk(md)
        if children:
            # 检查 Milvus 是否已有数据，有就跳过重建
            existing_count = 0
            try:
                existing_count = store.count()
            except Exception:
                pass

            if existing_count >= len(children) * 0.9:
                logger.info('Milvus 已有 %d 条数据，跳过重建', existing_count)
                bm25 = BM25Retriever(children)
            else:
                logger.info('Milvus 数据不足 (%d)，重新构建索引...', existing_count)
                vectors = embedder.encode([c.content for c in children])
                store.create(dim=embedder.dim)
                store.insert(children, vectors)
                bm25 = BM25Retriever(children)
                logger.info('索引构建完成: %d 子块', len(children))

    retriever = Retriever(store, bm25, embedder, reranker)
    _components.update({
        'embedder': embedder, 'store': store, 'bm25': bm25,
        'retriever': retriever, 'generator': generator,
        'query_understanding': query_understanding,
        'parents': parents, 'children': children,
    })
    logger.info('初始化完成: %d 父块, %d 子块', len(parents), len(children))
    return _components


# ========== 请求/响应模型 ==========

class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    page_filter: Optional[list] = None


class QueryResponse(BaseModel):
    answer: str
    sources: list
    query_analysis: dict  # Query 理解结果


class QueryAnalysisResponse(BaseModel):
    original_query: str
    intent: str
    intent_description: str
    disambiguated_query: str
    sub_queries: List[str]
    keywords: List[str]
    confidence: float


# ========== 异常处理 ==========

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error('未处理异常: %s %s -> %s', request.method, request.url.path, str(exc), exc_info=True)
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=500, content={'error': str(exc)})


# ========== 健康检查 ==========

@router.get('/health')
async def health():
    return {'status': 'ok', 'initialized': bool(_components)}


# ========== Query 理解接口 ==========

@router.post('/query/analyze', response_model=QueryAnalysisResponse)
async def analyze_query(req: QueryRequest):
    """分析用户问题（意图识别、消歧、分解）"""
    comp = _init()
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


# ========== 问答接口 ==========


# 问候语/闲聊关键词，这些不需要检索文档
_GREETING_PATTERNS = [
    '你好', '您好', '嗨', '哈喽', 'hello', 'hi', 'hey',
    '谢谢', '感谢', 'thanks', 'thank you',
    '再见', '拜拜', 'bye', 'goodbye',
    '你是谁', '你是谁啊', '你叫什么', '你是什么',
    '能做什么', '你能做什么', '怎么用', '怎么使用',
    '早上好', '下午好', '晚上好', '晚安',
    '好的', '知道了', '明白', 'ok', 'okay',
]

def _is_greeting(question: str) -> bool:
    """判断是否为问候语/闲聊，不需要检索文档"""
    q = question.strip().lower().rstrip('？?！!。.，,')
    return q in _GREETING_PATTERNS

def _search_with_query_understanding(comp: dict, question: str, top_k: int, page_filter: list = None):
    """使用 Query 理解进行检索"""
    qu = comp['query_understanding']
    retriever = comp['retriever']
    
    # 1. 分析问题
    analysis = qu.analyze(question)
    logger.info('Query 分析: intent=%s, sub_queries=%d', analysis.intent, len(analysis.sub_queries))
    
    # 2. 获取搜索查询
    search_queries = qu.get_search_queries(analysis)
    logger.info('搜索查询: %s', search_queries)
    
    # 3. 对每个查询进行检索
    all_results = []
    seen_chunk_ids = set()
    
    for query in search_queries:
        results = retriever.search(query, top_k=top_k, page_filter=page_filter)
        for r in results:
            if r['chunk_id'] not in seen_chunk_ids:
                all_results.append(r)
                seen_chunk_ids.add(r['chunk_id'])
    
    # 4. 按分数排序，取 top_k
    all_results.sort(key=lambda x: x.get('score', 0), reverse=True)
    return all_results[:top_k], analysis


@router.post('/query', response_model=QueryResponse)
async def query(req: QueryRequest):
    """非流式问答（带 Query 理解）"""
    comp = _init()
    
    # 问候语/闲聊：直接用 LLM 回复，不走检索
    if _is_greeting(req.question):
        logger.info('问候语/闲聊，跳过检索: %s', req.question)
        answer = comp['generator'].generate(req.question, [])
        return QueryResponse(
            answer=answer,
            sources=[],
            query_analysis={
                'intent': 'greeting',
                'intent_description': '问候或闲聊',
                'disambiguated_query': req.question,
                'sub_queries': [req.question],
                'keywords': [],
                'confidence': 1.0,
            },
        )
    
    # 使用 Query 理解进行检索
    results, analysis = _search_with_query_understanding(
        comp, req.question, req.top_k, req.page_filter
    )
    
    parent_ids = set(r['parent_id'] for r in results)
    parent_chunks = [p for p in comp['parents'] if p.chunk_id in parent_ids]
    if not parent_chunks and results:
        parent_chunks = [type('Ctx', (), {'content': r['content'], 'metadata': {'section_title': r.get('section_title', '')}})() for r in results]
    
    answer = comp['generator'].generate(req.question, parent_chunks)
    
    return QueryResponse(
        answer=answer,
        sources=[{'chunk_id': r['chunk_id'], 'section_title': r.get('section_title', ''), 'content': r['content'][:200]} for r in results],
        query_analysis={
            'intent': analysis.intent,
            'intent_description': analysis.intent_description,
            'disambiguated_query': analysis.disambiguated_query,
            'sub_queries': analysis.sub_queries,
            'keywords': analysis.keywords,
            'confidence': analysis.confidence,
        },
    )



class CompareResponse(BaseModel):
    """RAG vs LLM 对比结果"""
    rag_answer: str
    rag_sources: list
    llm_answer: str
    response_time_ms: int

@router.post('/query/compare', response_model=CompareResponse)
async def query_compare(req: QueryRequest):
    """RAG 答案 vs 纯 LLM 答案对比"""
    import time
    comp = _init()
    start = time.time()

    # 1. RAG 答案（带检索）
    results, analysis = _search_with_query_understanding(
        comp, req.question, req.top_k, req.page_filter
    )
    parent_ids = set(r['parent_id'] for r in results)
    parent_chunks = [p for p in comp['parents'] if p.chunk_id in parent_ids]
    if not parent_chunks and results:
        parent_chunks = [type('Ctx', (), {'content': r['content'], 'metadata': {'section_title': r.get('section_title', '')}})() for r in results]
    rag_answer = comp['generator'].generate(req.question, parent_chunks)

    # 2. 纯 LLM 答案（不检索）
    llm_answer = comp['generator'].generate(req.question, [])

    elapsed = int((time.time() - start) * 1000)
    logger.info('对比完成: RAG耗时=%dms', elapsed)

    return CompareResponse(
        rag_answer=rag_answer,
        rag_sources=[{'chunk_id': r['chunk_id'], 'section_title': r.get('section_title', ''), 'content': r['content'][:200]} for r in results],
        llm_answer=llm_answer,
        response_time_ms=elapsed,
    )
@router.post('/ingest')
async def ingest(file: UploadFile = File(...)):
    """上传并解析文档"""
    comp = _init()
    data_dir = Path(os.getenv('DATA_DIR', './data'))
    data_dir.mkdir(exist_ok=True)
    pdf_path = data_dir / file.filename
    with open(pdf_path, 'wb') as f:
        f.write(await file.read())
    from scripts.pipeline.batch_processor import BatchProcessor
    BatchProcessor(pdf_path=pdf_path, output_dir=data_dir).process()
    md_path = data_dir / (pdf_path.stem + '_refined.md')
    md = md_path.read_text(encoding='utf-8')
    from scripts.pipeline.chunker import Chunker
    parents, children = Chunker().chunk(md)
    comp['parents'], comp['children'] = parents, children
    vectors = comp['embedder'].encode([c.content for c in children])
    comp['store'].create(dim=comp['embedder'].dim)
    comp['store'].insert(children, vectors)
    comp['bm25'] = BM25Retriever(children)
    comp['retriever'] = Retriever(comp['store'], comp['bm25'], comp['embedder'], None)
    return {'status': 'ok', 'pages': len(parents), 'chunks': len(children)}


# ========== 聊天记录接口 ==========

class ChatCreate(BaseModel):
    chat_id: str
    title: str = "新对话"


class MessageCreate(BaseModel):
    msg_id: str
    role: str
    content: str
    sources: list = []
    query_analysis: Optional[dict] = None
    response_time: Optional[float] = None
    timestamp: Optional[float] = None


@router.get("/chats")
async def list_chats():
    return chat_store.get_chats()


@router.post("/chats")
async def create_chat(req: ChatCreate):
    return chat_store.create_chat(req.chat_id, req.title)


@router.get("/chats/{chat_id}/messages")
async def get_messages(chat_id: str):
    return chat_store.get_messages(chat_id)


@router.post("/chats/{chat_id}/messages")
async def add_message(chat_id: str, req: MessageCreate):
    chat_store.add_message(chat_id, req.msg_id, req.role, req.content, req.sources, req.timestamp, req.query_analysis, req.response_time)
    session_mem.add(chat_id, req.role, req.content)
    return {"status": "ok"}


@router.put("/chats/{chat_id}")
async def update_chat(chat_id: str, req: ChatCreate):
    chat_store.update_chat_title(chat_id, req.title)
    return {"status": "ok"}


@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str):
    chat_store.delete_chat(chat_id)
    session_mem.clear(chat_id)
    return {"status": "ok"}


@router.post("/query/stream")
async def query_stream(req: QueryRequest):
    """流式问答（带 Query 理解）"""
    comp = _init()

    # 问候语/闲聊：直接用 LLM 回复，不走检索
    if _is_greeting(req.question):
        logger.info('问候语/闲聊，跳过检索: %s', req.question)
        async def greeting_stream():
            try:
                for token in comp["generator"].generate_stream(req.question, []):
                    yield "data: " + _json.dumps({"type": "token", "data": token}, ensure_ascii=False) + "\n\n"
                yield "data: " + _json.dumps({"type": "done"}) + "\n\n"
            except Exception as e:
                yield "data: " + _json.dumps({"type": "error", "data": str(e)}, ensure_ascii=False) + "\n\n"
        return StreamingResponse(greeting_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # 使用 Query 理解进行检索
    results, analysis = _search_with_query_understanding(
        comp, req.question, req.top_k, req.page_filter
    )

    parent_ids = set(r["parent_id"] for r in results)
    parent_chunks = [p for p in comp["parents"] if p.chunk_id in parent_ids]
    if not parent_chunks and results:
        parent_chunks = [type('Ctx', (), {'content': r['content'], 'metadata': {'section_title': r.get('section_title', '')}})() for r in results]

    sources = [{"chunk_id": r["chunk_id"], "section_title": r.get("section_title", ''), "content": r["content"][:200]} for r in results]

    async def event_stream():
        try:
            yield "data: " + _json.dumps({
                "type": "query_analysis",
                "data": {
                    "intent": analysis.intent,
                    "intent_description": analysis.intent_description,
                    "disambiguated_query": analysis.disambiguated_query,
                    "sub_queries": analysis.sub_queries,
                    "keywords": analysis.keywords,
                    "confidence": analysis.confidence,
                }
            }, ensure_ascii=False) + "\n\n"
            yield "data: " + _json.dumps({"type": "sources", "data": sources}, ensure_ascii=False) + "\n\n"
            for token in comp["generator"].generate_stream(req.question, parent_chunks):
                yield "data: " + _json.dumps({"type": "token", "data": token}, ensure_ascii=False) + "\n\n"
            yield "data: " + _json.dumps({"type": "done"}) + "\n\n"
        except Exception as e:
            logger.error('流式生成出错: %s', str(e), exc_info=True)
            yield "data: " + _json.dumps({"type": "error", "data": str(e)}, ensure_ascii=False) + "\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# 注册路由
app.include_router(router)

# 启动时预加载模型，避免首次请求卡顿
@app.on_event('startup')
async def startup_event():
    import threading
    def _preload():
        try:
            logger.info('预加载模型...')
            _init()
            logger.info('预加载完成')
        except Exception as e:
            logger.error('预加载失败: %s', e)
    threading.Thread(target=_preload, daemon=True).start()


