"""文档上传和解析路由"""
import logging
import os
from pathlib import Path
from fastapi import APIRouter, UploadFile, File

from api.components import get_components

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post('/ingest')
async def ingest(file: UploadFile = File(...)):
    """上传并解析文档，追加到现有索引中（不清除旧数据）"""
    comp = get_components()
    data_dir = Path(os.getenv('DATA_DIR', './data'))
    storage_dir = Path(os.getenv('STORAGE_DIR', './storage'))
    data_dir.mkdir(exist_ok=True)
    pdf_path = data_dir / file.filename

    with open(pdf_path, 'wb') as f:
        f.write(await file.read())

    from scripts.pipeline.batch_processor import BatchProcessor
    from scripts.pipeline.chunker import Chunker

    # 检查状态文件是否可信
    md_path = data_dir / (pdf_path.stem + '_refined.md')
    state_path = storage_dir / (pdf_path.stem.replace(' ', '_') + '_status.json')
    if state_path.exists() and (not md_path.exists() or md_path.stat().st_size == 0):
        logger.warning('状态文件存在但输出为空，清理状态重新解析: %s', state_path.name)
        state_path.unlink(missing_ok=True)

    BatchProcessor(pdf_path=pdf_path, output_dir=data_dir).process()

    md = md_path.read_text(encoding='utf-8')
    source_file = md_path.name
    parents, children = Chunker().chunk(md, source_file=source_file)

    if not children:
        return {'status': 'ok', 'pages': 0, 'chunks': 0, 'warning': '文档解析结果为空，请检查 PDF 文件'}

    # 追加到现有分块列表
    comp['parents'].extend(parents)
    comp['children'].extend(children)

    # 编码并插入 Milvus
    vectors = comp['embedder'].encode([c.content for c in children])
    comp['store'].create(dim=comp['embedder'].dim)
    inserted, skipped = comp['store'].insert(children, vectors, source_file=source_file)
    logger.info('文档 %s 索引完成: 插入 %d 条, 跳过 %d 条重复', source_file, inserted, skipped)

    # 重建 BM25（包含所有文档）
    from scripts.pipeline.bm25_retriever import BM25Retriever
    from scripts.pipeline.retriever import Retriever
    comp['bm25'] = BM25Retriever(comp['children'])
    comp['retriever'] = Retriever(comp['store'], comp['bm25'], comp['embedder'], comp.get('reranker'))
    comp['retriever']._reranker_path = comp.get('rerank_path')

    return {'status': 'ok', 'pages': len(parents), 'chunks': len(children),
            'inserted': inserted, 'skipped': skipped}


@router.get('/ingest/progress')
async def get_ingest_progress():
    """获取当前文档解析进度"""
    from api.progress import get_progress
    return get_progress()