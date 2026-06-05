"""文档上传和解析路由 - 支持多文件上传和队列管理

功能：
  1. 支持多文件同时上传
  2. 文件加入队列，按顺序解析
  3. SSE 实时推送进度
  4. 第一个解析完自动开始第二个（接力）
"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import List
from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.init import get_components
from api.queue_manager import document_queue, TaskStatus

logger = logging.getLogger(__name__)
router = APIRouter()


class IngestResponse(BaseModel):
    """上传响应"""
    status: str
    message: str
    queue_length: int
    tasks: list


@router.post('/ingest')
async def ingest(files: List[UploadFile] = File(...)):
    """上传并解析文档（支持多文件）
    
    文件会加入队列，按顺序解析。第一个解析完自动开始下一个。
    返回队列状态，前端可通过 /ingest/progress 或 SSE 获取实时进度。
    """
    if not files:
        return {"status": "error", "message": "请选择文件"}

    data_dir = Path(os.getenv('DATA_DIR', './data'))
    data_dir.mkdir(exist_ok=True)

    added_tasks = []
    
    for file in files:
        if not file.filename.endswith('.pdf'):
            continue
        
        # 保存文件
        pdf_path = data_dir / file.filename
        with open(pdf_path, 'wb') as f:
            f.write(await file.read())
        
        # 添加到队列
        task = document_queue.add_task(file.filename, pdf_path)
        added_tasks.append(task.to_dict())

    # 如果没有正在处理的任务，启动处理
    if not document_queue._processing:
        asyncio.create_task(_process_queue())

    return {
        "status": "ok",
        "message": f"已添加 {len(added_tasks)} 个文件到队列",
        "queue_length": document_queue.get_queue_status()["queue_length"],
        "tasks": added_tasks,
    }


@router.get('/ingest/progress')
async def get_ingest_progress():
    """获取当前文档解析进度（兼容旧接口）"""
    return document_queue.get_current_progress()


@router.get('/ingest/queue')
async def get_queue_status():
    """获取队列状态"""
    return document_queue.get_queue_status()


@router.post('/ingest/pause')
async def pause_ingest():
    """暂停解析"""
    document_queue.pause()
    return {"status": "ok", "paused": True}


@router.post('/ingest/resume')
async def resume_ingest():
    """继续解析"""
    document_queue.resume()
    # 如果队列中有待处理任务，启动处理
    if not document_queue._processing:
        asyncio.create_task(_process_queue())
    return {"status": "ok", "paused": False}


@router.get('/ingest/stream')
async def stream_progress():
    """SSE 实时推送进度"""
    async def event_generator():
        queue = await document_queue.subscribe()
        try:
            while True:
                try:
                    status = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {json.dumps(status)}\n\n"
                except asyncio.TimeoutError:
                    # 发送心跳
                    yield f": heartbeat\n\n"
        finally:
            document_queue.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


async def _process_queue():
    """处理队列中的任务（接力机制，支持暂停）"""
    while True:
        # 检查是否暂停
        while document_queue.is_paused:
            await asyncio.sleep(1)

        task = document_queue.get_next_task()
        if not task:
            break

        document_queue.start_task(task)

        try:
            await _process_single_document(task)
            document_queue.complete_task(task)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error("文档处理失败: %s - %s\n%s", task.filename, str(e), tb)
            error_msg = str(e) if str(e) else f"处理异常: {type(e).__name__}"
            document_queue.fail_task(task, error_msg)

        # 短暂等待，让前端有时间更新状态
        await asyncio.sleep(0.5)

    logger.info("队列处理完成")


async def _process_single_document(task):
    """处理单个文档"""
    from scripts.pipeline.batch_processor import BatchProcessor
    from scripts.pipeline.chunker import Chunker
    from api.progress import get_progress

    data_dir = Path(os.getenv('DATA_DIR', './data'))
    storage_dir = Path(os.getenv('STORAGE_DIR', './storage'))
    
    pdf_path = task.file_path
    md_path = data_dir / (pdf_path.stem + '_refined.md')
    state_path = storage_dir / (pdf_path.stem.replace(' ', '_') + '_status.json')

    # 检查状态文件是否可信
    if state_path.exists() and (not md_path.exists() or md_path.stat().st_size == 0):
        logger.warning('状态文件存在但输出为空，清理状态重新解析: %s', state_path.name)
        state_path.unlink(missing_ok=True)

    # 处理文档
    processor = BatchProcessor(pdf_path=pdf_path, output_dir=data_dir)
    
    # 更新进度：开始渲染
    document_queue.update_current_progress(stage="rendering")
    
    # 启动进度同步任务：每1秒把 api/progress 的进度同步到 queue_manager
    async def _sync_progress():
        while True:
            await asyncio.sleep(1)
            p = get_progress()
            # 有数据就同步，不管 active 状态（由外部 cancel 控制生命周期）
            if p.get('total_pages', 0) > 0:
                document_queue.update_current_progress(
                    total_pages=p.get('total_pages', 0),
                    completed_pages=p.get('completed_pages', 0),
                    current_batch=p.get('current_batch', 0),
                    total_batches=p.get('total_batches', 0),
                    stage=p.get('stage', 'ocr'),
                )

    sync_task = asyncio.create_task(_sync_progress())

    # 在线程池中运行，避免阻塞事件循环（SSE推送依赖事件循环）
    loop = asyncio.get_event_loop()
    report = await loop.run_in_executor(None, processor.process)

    # 处理完成，停止同步任务
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass

    # 索引到 Milvus
    document_queue.update_current_progress(stage="indexing")
    
    comp = get_components()
    md = md_path.read_text(encoding='utf-8')
    source_file = md_path.name
    parents, children = Chunker().chunk(md, source_file=source_file)

    if not children:
        logger.warning('文档解析结果为空: %s', task.filename)
        return

    # 追加到现有分块列表
    comp['parents'].extend(parents)
    comp['children'].extend(children)

    # 编码并插入 Milvus
    vectors = comp['embedder'].encode([c.content for c in children])
    comp['store'].create(dim=comp['embedder'].dim)
    inserted, skipped = comp['store'].insert(children, vectors, source_file=source_file)
    logger.info('文档 %s 索引完成: 插入 %d 条, 跳过 %d 条重复', source_file, inserted, skipped)

    # 重建 BM25
    from scripts.pipeline.bm25_retriever import BM25Retriever
    from scripts.pipeline.retriever import Retriever
    comp['bm25'] = BM25Retriever(comp['children'])
    comp['retriever'] = Retriever(comp['store'], comp['bm25'], comp['embedder'], comp.get('reranker'))
    comp['retriever']._rerank_path = comp.get('rerank_path')
    
    # 更新进度：完成
    document_queue.update_current_progress(
        total_pages=report.total_pages,
        completed_pages=report.total_pages,
        stage="done"
    )

    # 释放内存：清理页面图片和 PDF 对象
    import gc
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.info('GPU 缓存已释放')
    except ImportError:
        pass
    logger.info('文档 %s 处理完成，内存已释放', task.filename)