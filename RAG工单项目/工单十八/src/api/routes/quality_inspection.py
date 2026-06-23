from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from src.agents.skill_manager import build_skill_manager
from src.agents.workflows.document_ingestion_workflow import DocumentIngestionWorkflow
from src.core.settings import get_settings
from src.core.task_store import TaskStore
from src.models.api_models import QualityInspectionRequest
from src.models.task_models import InspectionTaskState

router = APIRouter()
_task_store = TaskStore()
_workflow = DocumentIngestionWorkflow()


@router.post("/v1/document/quality-inspection")
async def create_quality_inspection(request: QualityInspectionRequest):
    """创建文档质检任务，支持同步和异步。"""

    mode = _resolve_mode(request)
    if mode == "sync":
        result = build_skill_manager().run("document-quality-assessment", request)
        return {
            "task_id": result.task_id,
            "status": result.status,
            "progress": result.progress,
            "report": result.report.model_dump() if result.report else None,
            "html_path": result.report.html_report.html_path if result.report else None,
            "html_content": result.report.html_report.html_content if result.report else None,
            "error_message": result.error_message,
        }

    task = _task_store.create(request.model_dump())
    thread = threading.Thread(target=_run_async_task, args=(task.task_id,), daemon=True)
    thread.start()
    return JSONResponse(
        status_code=202,
        content={
            "task_id": task.task_id,
            "status": task.status,
            "status_url": f"/v1/document/quality-inspection/{task.task_id}",
        },
    )


@router.get("/v1/document/quality-inspection/{task_id}")
async def get_quality_inspection_status(task_id: str):
    """查看异步任务状态。"""

    task = _task_store.load(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "task_id": task.task_id,
        "status": task.status,
        "progress": task.progress,
        "report": task.report,
        "html_path": task.html_path,
        "html_content": task.html_content,
        "error_message": task.error_message,
    }


@router.post("/v1/document/quality-inspection/{task_id}/resume")
async def resume_quality_inspection(task_id: str):
    """重新执行失败任务。"""

    task = _task_store.load(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    task.status = "pending"
    task.progress = 0
    task.current_step = "pending"
    task.failed_step = None
    task.error_message = None
    task.started_at = time.time()
    task.finished_at = None
    _task_store.save(task)
    thread = threading.Thread(target=_run_async_task, args=(task.task_id,), daemon=True)
    thread.start()
    return JSONResponse(
        status_code=202,
        content={"task_id": task.task_id, "status": task.status},
    )


def _run_async_task(task_id: str) -> None:
    """后台执行异步任务。"""

    task = _task_store.load(task_id)
    if task is None:
        return
    task.status = "running"
    task.current_step = "collect_inputs"
    task.progress = 10
    _task_store.save(task)

    request = QualityInspectionRequest.model_validate(task.request_payload)
    result = _workflow.run(request, task)
    task.status = result.status
    task.progress = 100
    _task_store.save(task)


def _resolve_mode(request: QualityInspectionRequest) -> str:
    """auto 模式下按文件数量和体积自动判断。"""

    if request.mode != "auto":
        return request.mode
    settings = get_settings()
    selected_paths = request.file_paths or []
    if request.folder_path and not selected_paths:
        selected_paths = [str(path) for path in Path(request.folder_path).iterdir() if path.is_file()]
    total_size = 0
    for file_path in selected_paths:
        path = Path(file_path)
        if path.exists():
            total_size += path.stat().st_size
    total_size_mb = total_size / 1024 / 1024
    if len(selected_paths) > settings.async_file_count_threshold or total_size_mb > settings.async_total_size_threshold_mb:
        return "async"
    return "sync"
