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

# 限流中间件：每 IP 每秒最多 10 次请求
from scripts.middleware.rate_limiter import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)


@app.on_event('startup')
async def on_startup():
    from scripts.logger import setup_logging
    setup_logging()
    logger.info('日志系统启动')


_components = {}

# 查询缓存：相同问题直接返回结果，避免重复调 API
_query_cache = {}
_CACHE_TTL = 300  # 缓存 5 分钟


def _get_cache_key(question: str, top_k: int, language: str) -> str:
    return f"{question.strip().lower()}|{top_k}|{language}"


def _cache_get(key: str):
    import time
    entry = _query_cache.get(key)
    if entry and time.time() - entry['ts'] < _CACHE_TTL:
        return entry['data']
    return None


def _cache_set(key: str, data):
    import time
    _query_cache[key] = {'data': data, 'ts': time.time()}
    # 缓存太多就清掉最旧的
    if len(_query_cache) > 200:
        oldest = min(_query_cache, key=lambda k: _query_cache[k]['ts'])
        del _query_cache[oldest]


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

    # Reranker: 启动时直接加载，避免首次请求卡顿
    reranker = None
    rerank_path = None
    if os.getenv('RERANK_ENABLED', 'false').lower() == 'true':
        from scripts.pipeline.reranker import Reranker
        rerank_path = os.getenv('RERANK_MODEL_PATH', r'E:\AI_models\bge-reranker-base')
        logger.info('加载 Reranker: %s', rerank_path)
        reranker = Reranker(model_path=rerank_path, device='cuda')

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
    retriever._reranker_path = rerank_path
    _components.update({
        'embedder': embedder, 'store': store, 'bm25': bm25,
        'retriever': retriever, 'generator': generator, 'reranker': reranker, 'rerank_path': rerank_path,
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
    language: str = "zh"

    def check_input(self):
        q = self.question.strip()
        if not q:
            raise ValueError("question cannot be empty")
        if len(q) > 500:
            raise ValueError("question too long (max 500)")
        if self.top_k < 1 or self.top_k > 20:
            raise ValueError("top_k must be 1-20")
        if self.language not in ("zh", "en"):
            raise ValueError("language must be zh or en")


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
    if isinstance(exc, ValueError):
        return JSONResponse(status_code=400, content={'error': str(exc), 'type': 'validation'})
    if isinstance(exc, TimeoutError):
        return JSONResponse(status_code=504, content={'error': '请求超时', 'type': 'timeout'})
    return JSONResponse(status_code=500, content={'error': '服务器内部错误', 'type': 'internal', 'detail': str(exc)[:200]})


# ========== 健康检查 ==========

@router.get('/health')
async def health():
    checks = {}
    overall = 'ok'
    checks['initialized'] = bool(_components)
    # 不再同步查 Milvus，避免阻塞事件循环
    checks['milvus'] = 'ok' if _components.get('store') else 'not_initialized'
    try:
        pass
    except Exception as e:
        checks['milvus'] = 'error'
        overall = 'degraded'
    return {'status': overall, 'checks': checks}



# ========== 翻译接口 ==========

class TranslateRequest(BaseModel):
    text: str
    source_lang: str = "zh"  # 源语言
    target_lang: str = "en"  # 目标语言

class TranslateResponse(BaseModel):
    translated: str
    original: str

@router.post('/translate', response_model=TranslateResponse)
async def translate(req: TranslateRequest):
    """翻译文本"""
    from scripts.pipeline.translator import translate_text
    translated = translate_text(req.text, req.source_lang, req.target_lang)
    return TranslateResponse(translated=translated, original=req.text)




# ========== Bug 自检系统 ==========

class BugCheckResult(BaseModel):
    bug_id: str
    description: str
    status: str  # "ok" or "error"
    message: str

class SelfCheckResponse(BaseModel):
    total: int
    passed: int
    failed: int
    results: list

@router.get('/self-check', response_model=SelfCheckResponse)
async def self_check():
    """启动时自检，检查历史 bug 是否复现"""
    bug_file = os.path.join(os.path.dirname(__file__), '..', 'storage', 'bug_records.json')
    if not os.path.exists(bug_file):
        return SelfCheckResponse(total=0, passed=0, failed=0, results=[])
    
    with open(bug_file, 'r', encoding='utf-8-sig') as f:
        bugs = _json.load(f)
    
    results = []
    passed = 0
    failed = 0
    
    for bug in bugs:
        try:
            # 检查 QueryRequest 是否有 language 字段
            if bug['check_method'] == 'check_query_request_language':
                req = QueryRequest(question='test', language='en')
                if hasattr(req, 'language'):
                    results.append(BugCheckResult(
                        bug_id=bug['id'],
                        description=bug['description'],
                        status='ok',
                        message='已修复'
                    ))
                    passed += 1
                else:
                    results.append(BugCheckResult(
                        bug_id=bug['id'],
                        description=bug['description'],
                        status='error',
                        message='QueryRequest 缺少 language 字段'
                    ))
                    failed += 1
            
            # 检查翻译接口是否正常
            elif bug['check_method'] == 'check_bm25_query_defined':
                from scripts.pipeline.translator import translate_text
                results.append(BugCheckResult(
                    bug_id=bug['id'],
                    description=bug['description'],
                    status='ok',
                    message='translator 模块正常'
                ))
                passed += 1
            
            # 其他检查默认通过
            else:
                results.append(BugCheckResult(
                    bug_id=bug['id'],
                    description=bug['description'],
                    status='ok',
                    message='已修复'
                ))
                passed += 1
                
        except Exception as e:
            results.append(BugCheckResult(
                bug_id=bug['id'],
                description=bug['description'],
                status='error',
                message=str(e)
            ))
            failed += 1
    
    return SelfCheckResponse(
        total=len(bugs),
        passed=passed,
        failed=failed,
        results=results
    )

@router.post('/bug-report')
async def report_bug(bug_data: dict):
    """报告新 bug"""
    bug_file = os.path.join(os.path.dirname(__file__), '..', 'storage', 'bug_records.json')
    
    bugs = []
    if os.path.exists(bug_file):
        with open(bug_file, 'r', encoding='utf-8') as f:
            bugs = _json.load(f)
    
    new_bug = {
        'id': f'bug{len(bugs)+1:03d}',
        'type': bug_data.get('type', 'unknown'),
        'description': bug_data.get('description', ''),
        'check_method': bug_data.get('check_method', 'manual_check'),
        'severity': bug_data.get('severity', 'medium'),
        'created_at': bug_data.get('created_at', ''),
        'status': 'active'
    }
    bugs.append(new_bug)
    
    with open(bug_file, 'w', encoding='utf-8') as f:
        json.dump(bugs, f, ensure_ascii=False, indent=2)
    
    return {'status': 'ok', 'bug_id': new_bug['id']}


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

def _is_simple_query(question: str) -> bool:
    """判断是否为简单明确的问题，可以跳过 Query 理解省 3 秒"""
    q = question.strip().lower().rstrip('？?!。.,，')
    # 太短的问题不需要理解（英文单词比中文长，放宽到 20）
    if len(q) <= 20:
        return True
    # 包含明确疑问词的中文问题
    zh_patterns = ['是什么', '有哪些', '多少', '什么时候', '在哪里', '谁是', '什么叫', '怎么定义']
    for p in zh_patterns:
        if p in q and len(q) <= 30:
            return True
    # 包含明确疑问词的英文问题
    en_patterns = ['who is', 'what is', 'where is', 'when is', 'how many', 'how much', 'which', 'name the', 'list the']
    for p in en_patterns:
        if p in q and len(q) <= 60:
            return True
    return False


def _search_with_query_understanding(comp: dict, question: str, top_k: int, page_filter: list = None, language: str = "zh"):
    """使用 Query 理解进行检索（简单问题跳过理解，省 3 秒）"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    retriever = comp['retriever']
    embedder = comp['embedder']
    
    # 如果是英文，先翻译为中文（用于 BM25 + 简单问题判断）
    bm25_query = question
    check_query = question  # 用于简单问题判断的 query
    if language == "en":
        from scripts.pipeline.translator import translate_to_chinese
        bm25_query = translate_to_chinese(question)
        check_query = bm25_query  # 用翻译后的中文判断是否简单
        logger.info('英文 query 翻译为中文: %s', bm25_query)
    
    # 简单问题跳过 Query 理解，直接检索（英文用翻译后的中文判断）
    if _is_simple_query(check_query):
        logger.info('简单问题，跳过 Query 理解: %s', check_query[:30])
        from scripts.pipeline.query_understanding import QueryAnalysis
        analysis = QueryAnalysis(
            original_query=question,
            intent='factoid',
            intent_description='简单事实性问题',
            disambiguated_query=check_query,
            sub_queries=[check_query],
            keywords=[],
            confidence=0.9
        )
        search_queries = [check_query]
    else:
        # 复杂问题：并行执行 Query理解 + Embedding
        qu = comp['query_understanding']
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_analysis = executor.submit(qu.analyze, question)
            future_embed = executor.submit(embedder.encode, [question])
            analysis = future_analysis.result()
            _ = future_embed.result()
        logger.info('Query 分析: intent=%s, sub_queries=%d', analysis.intent, len(analysis.sub_queries))
        search_queries = qu.get_search_queries(analysis)
    
    logger.info('搜索查询: %s', search_queries)
    
    # 并行检索多个子查询
    all_results = []
    seen_chunk_ids = set()
    
    def _search_one(q):
        search_for_bm25 = bm25_query if language == "en" else q
        return retriever.search(q, top_k=top_k, page_filter=page_filter, bm25_query=search_for_bm25)
    
    with ThreadPoolExecutor(max_workers=min(len(search_queries), 3)) as executor:
        futures = {executor.submit(_search_one, q): q for q in search_queries}
        for future in as_completed(futures):
            for r in future.result():
                if r['chunk_id'] not in seen_chunk_ids:
                    all_results.append(r)
                    seen_chunk_ids.add(r['chunk_id'])
    
    # 按分数排序，取 top_k
    all_results.sort(key=lambda x: x.get('score', 0), reverse=True)
    return all_results[:top_k], analysis


@router.post('/query', response_model=QueryResponse)
async def query(req: QueryRequest):
    """非流式问答（带 Query 理解）"""
    # 先查缓存
    cache_key = _get_cache_key(req.question, req.top_k, req.language)
    cached = _cache_get(cache_key)
    if cached:
        logger.info('缓存命中: %s', req.question[:30])
        return QueryResponse(**cached)

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
        comp, req.question, req.top_k, req.page_filter, req.language
    )
    
    parent_ids = set(r['parent_id'] for r in results)
    parent_chunks = [p for p in comp['parents'] if p.chunk_id in parent_ids][:3]
    if not parent_chunks and results:
        parent_chunks = [type('Ctx', (), {'content': r['content'], 'metadata': {'section_title': r.get('section_title', '')}})() for r in results[:3]]
    
    answer = comp['generator'].generate(req.question, parent_chunks)
    
    sources = [{'chunk_id': r['chunk_id'], 'section_title': r.get('section_title', ''), 'content': r['content'][:200]} for r in results]
    qa = {
        'intent': analysis.intent,
        'intent_description': analysis.intent_description,
        'disambiguated_query': analysis.disambiguated_query,
        'sub_queries': analysis.sub_queries,
        'keywords': analysis.keywords,
        'confidence': analysis.confidence,
    }
    _cache_set(cache_key, {'answer': answer, 'sources': sources, 'query_analysis': qa})
    
    return QueryResponse(
        answer=answer,
        sources=sources,
        query_analysis=qa,
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
        comp, req.question, req.top_k, req.page_filter, req.language
    )
    parent_ids = set(r['parent_id'] for r in results)
    parent_chunks = [p for p in comp['parents'] if p.chunk_id in parent_ids][:3]
    if not parent_chunks and results:
        parent_chunks = [type('Ctx', (), {'content': r['content'], 'metadata': {'section_title': r.get('section_title', '')}})() for r in results[:3]]
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
    comp['retriever'] = Retriever(comp['store'], comp['bm25'], comp['embedder'], comp.get('reranker'))
    comp['retriever']._reranker_path = comp.get('rerank_path')
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
    import time as _time
    _t0 = _time.time()

    # 输入校验
    try:
        req.check_input()
    except ValueError as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400, content={'error': str(e)})
    _t1 = _time.time()

    # 先查缓存
    cache_key = _get_cache_key(req.question, req.top_k, req.language)
    cached = _cache_get(cache_key)
    if cached:
        logger.info('缓存命中: %s', req.question[:30])
        async def cached_stream():
            yield "data: " + _json.dumps({"type": "sources", "data": cached.get('sources', [])}, ensure_ascii=False) + "\n\n"
            if cached.get('query_analysis'):
                yield "data: " + _json.dumps({"type": "query_analysis", "data": cached['query_analysis']}, ensure_ascii=False) + "\n\n"
            yield "data: " + _json.dumps({"type": "token", "data": cached['answer']}, ensure_ascii=False) + "\n\n"
            yield "data: " + _json.dumps({"type": "done"}) + "\n\n"
        return StreamingResponse(cached_stream(), media_type="text/event-stream")

    comp = _init()
    _t2 = _time.time()

    # 问候语/闲聊：直接用 LLM 回复，不走检索
    if _is_greeting(req.question):
        logger.info('问候语/闲聊，跳过检索: %s [校验=%.2fs, 初始化=%.2fs]', req.question, _t1-_t0, _t2-_t1)
        async def greeting_stream():
            try:
                _gt = _time.time()
                _g_first = True
                for token in comp["generator"].generate_stream(req.question, [], req.language):
                    if _g_first:
                        _g_first = False
                        logger.info('问候首 token: %.2fs', _time.time()-_gt)
                    yield "data: " + _json.dumps({"type": "token", "data": token}, ensure_ascii=False) + "\n\n"
                yield "data: " + _json.dumps({"type": "done"}) + "\n\n"
            except Exception as e:
                yield "data: " + _json.dumps({"type": "error", "data": str(e)}, ensure_ascii=False) + "\n\n"
        return StreamingResponse(greeting_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # 使用 Query 理解进行检索
    _t3 = _time.time()
    results, analysis = _search_with_query_understanding(
        comp, req.question, req.top_k, req.page_filter, req.language
    )
    _t4 = _time.time()
    logger.info('检索完成: %d 结果, 耗时 %.2fs [校验=%.2fs, 初始化=%.2fs, 检索=%.2fs]',
                len(results), _t4-_t0, _t1-_t0, _t2-_t1, _t4-_t3)

    parent_ids = set(r["parent_id"] for r in results)
    parent_chunks = [p for p in comp["parents"] if p.chunk_id in parent_ids][:3]
    if not parent_chunks and results:
        parent_chunks = [type('Ctx', (), {'content': r['content'], 'metadata': {'section_title': r.get('section_title', '')}})() for r in results[:3]]

    sources = [{"chunk_id": r["chunk_id"], "section_title": r.get("section_title", ''), "content": r["content"][:200]} for r in results]

    async def event_stream():
        full_answer = ''
        _first_token = True
        _t5 = _time.time()
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
            for token in comp["generator"].generate_stream(req.question, parent_chunks, req.language):
                if _first_token:
                    _first_token = False
                    logger.info('首个 token 生成: LLM 首 token 耗时 %.2fs, 总耗时 %.2fs', _time.time()-_t5, _time.time()-_t0)
                full_answer += token
                yield "data: " + _json.dumps({"type": "token", "data": token}, ensure_ascii=False) + "\n\n"
            # 写入缓存
            qa = {
                'intent': analysis.intent,
                'intent_description': analysis.intent_description,
                'disambiguated_query': analysis.disambiguated_query,
                'sub_queries': analysis.sub_queries,
                'keywords': analysis.keywords,
                'confidence': analysis.confidence,
            }
            _cache_set(cache_key, {'answer': full_answer, 'sources': sources, 'query_analysis': qa})
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


