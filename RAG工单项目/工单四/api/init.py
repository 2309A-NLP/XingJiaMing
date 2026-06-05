"""组件初始化模块

懒加载所有 RAG 组件，启动时预加载避免首次请求卡顿。
支持多文档共存，新文档入库时自动去重。
分块结果缓存到 storage/chunks_cache.pkl，避免每次启动重复分块。
"""
import logging
import os
import pickle
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv

load_dotenv(override=True)
logger = logging.getLogger(__name__)

_components: Dict[str, Any] = {}

# 分块缓存路径
_CHUNKS_CACHE = Path(__file__).parent.parent / 'storage' / 'chunks_cache.pkl'


def _load_chunks_cache() -> dict:
    """加载分块缓存，返回 {source_file: (parents, children)}"""
    if _CHUNKS_CACHE.exists():
        try:
            with open(_CHUNKS_CACHE, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            logger.warning('分块缓存加载失败，将重新分块: %s', e)
    return {}


def _save_chunks_cache(cache: dict) -> None:
    """保存分块缓存"""
    _CHUNKS_CACHE.parent.mkdir(exist_ok=True)
    with open(_CHUNKS_CACHE, 'wb') as f:
        pickle.dump(cache, f)


def _load_all_documents(data_dir: Path, chunker, embedder, store) -> tuple:
    """加载 data 目录下所有已解析的 markdown 文档"""
    md_files = sorted(data_dir.glob('*_refined.md'), key=lambda f: f.stat().st_mtime)
    if not md_files:
        logger.info('未找到已解析文档，请先上传 PDF')
        return [], []

    chunks_cache = _load_chunks_cache()
    cache_changed = False
    all_parents, all_children = [], []

    for md_path in md_files:
        source_file = md_path.name

        # 检查缓存
        if source_file in chunks_cache:
            parents, children = chunks_cache[source_file]
            logger.info('文档 %s 从缓存加载分块: %d 父块, %d 子块', source_file, len(parents), len(children))
        else:
            logger.info('文档 %s 重新分块...', source_file)
            md = md_path.read_text(encoding='utf-8')
            parents, children = chunker.chunk(md, source_file=source_file)
            chunks_cache[source_file] = (parents, children)
            cache_changed = True
            logger.info('文档 %s 分块完成: %d 父块, %d 子块', source_file, len(parents), len(children))

        all_parents.extend(parents)
        all_children.extend(children)

        # 检查是否已在 Milvus 中
        existing = store.query_by_source(source_file)
        if existing:
            logger.info('文档 %s 已在 Milvus 中 (%d 条)，跳过索引', source_file, len(existing))
            continue

        # 新文档，编码并插入
        logger.info('文档 %s 开始索引...', source_file)
        vectors = embedder.encode([c.content for c in children])
        inserted, skipped = store.insert(children, vectors, source_file=source_file)
        logger.info('文档 %s 索引完成: 插入 %d 条, 跳过 %d 条重复', source_file, inserted, skipped)

    if cache_changed:
        _save_chunks_cache(chunks_cache)
        logger.info('分块缓存已保存')

    return all_parents, all_children


def get_components() -> Dict[str, Any]:
    """获取已初始化的组件（懒加载）"""
    if _components:
        return _components

    from scripts.pipeline.chunker import Chunker
    from scripts.pipeline.embedder import Embedder
    from scripts.pipeline.vector_store import VectorStore
    from scripts.pipeline.bm25_retriever import BM25Retriever
    from scripts.pipeline.retriever import Retriever
    from scripts.pipeline.llm_generator import Generator
    from scripts.pipeline.query_understanding import QueryUnderstanding
    from scripts.pipeline.vision_analyzer import VisionAnalyzer

    logger.info('开始初始化组件...')

    embedding_path = os.getenv('EMBEDDING_MODEL_PATH', '')
    milvus_host = os.getenv('MILVUS_HOST', 'localhost')
    milvus_port = os.getenv('MILVUS_PORT', '19530')
    collection = os.getenv('MILVUS_COLLECTION', 'rag_workorder4')
    data_dir = Path(os.getenv('DATA_DIR', './data'))

    embedder = Embedder(model_path=embedding_path)
    store = VectorStore(host=milvus_host, port=int(milvus_port), collection=collection)

    reranker = None
    rerank_path = None
    if os.getenv('RERANK_ENABLED', 'false').lower() == 'true':
        from scripts.pipeline.reranker import Reranker
        rerank_path = os.getenv('RERANK_MODEL_PATH', '')
        if rerank_path:
            logger.info('加载 Reranker: %s', rerank_path)
            reranker = Reranker(model_path=rerank_path, device='cuda')
        else:
            logger.warning('RERANK_ENABLED=true 但 RERANK_MODEL_PATH 未配置，跳过 Reranker')

    generator = Generator()

    # 多模态图片解析器（可选）
    vision_enabled = os.getenv('VISION_ENABLED', 'false').lower() == 'true'
    vision = VisionAnalyzer() if vision_enabled else None
    if vision_enabled and vision and not vision.is_available:
        logger.warning('VISION_ENABLED=true 但 API 未配置')
        vision = None

    query_understanding = QueryUnderstanding()
    chunker = Chunker()

    store.create(dim=embedder.dim)

    # 加载所有文档
    parents, children = _load_all_documents(data_dir, chunker, embedder, store)

    bm25 = BM25Retriever(children)
    total_in_milvus = store.count()
    logger.info('Milvus 共 %d 条数据, BM25 共 %d 个分块', total_in_milvus, len(children))

    retriever = Retriever(store, bm25, embedder, reranker)
    retriever._reranker_path = rerank_path
    _components.update({
        'embedder': embedder, 'store': store, 'bm25': bm25,
        'retriever': retriever, 'generator': generator, 'vision': vision, 'reranker': reranker,
        'rerank_path': rerank_path,
        'query_understanding': query_understanding,
        'parents': parents, 'children': children,
    })
    logger.info('初始化完成: %d 父块, %d 子块', len(parents), len(children))
    return _components