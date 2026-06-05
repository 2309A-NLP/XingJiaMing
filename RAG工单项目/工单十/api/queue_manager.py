"""文档队列管理器 - 支持多文件上传和接力解析

功能：
  1. 维护一个待解析的文档队列
  2. 按顺序逐个解析，第一个完成自动开始下一个
  3. 实时推送进度（SSE）
  4. 支持查看队列状态
"""
from __future__ import annotations
import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """任务状态"""
    WAITING = "waiting"      # 等待中
    PROCESSING = "processing"  # 解析中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失败


@dataclass
class DocumentTask:
    """单个文档任务"""
    task_id: str
    filename: str
    file_path: Path
    status: TaskStatus = TaskStatus.WAITING
    total_pages: int = 0
    completed_pages: int = 0
    current_batch: int = 0
    total_batches: int = 0
    stage: str = ""
    error: Optional[str] = None
    start_time: float = 0
    end_time: float = 0
    batch_times: List[float] = field(default_factory=list)

    @property
    def progress_percent(self) -> float:
        if self.total_pages == 0:
            return 0
        return round(self.completed_pages / self.total_pages * 100, 1)

    @property
    def eta_seconds(self) -> float:
        if not self.batch_times or self.current_batch == 0:
            return 0
        avg_time = sum(self.batch_times) / len(self.batch_times)
        remaining = self.total_batches - self.current_batch
        return round(avg_time * remaining, 1)

    @property
    def elapsed_seconds(self) -> float:
        if self.start_time == 0:
            return 0
        end = self.end_time if self.end_time > 0 else time.time()
        return round(end - self.start_time, 1)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "filename": self.filename,
            "status": self.status.value,
            "total_pages": self.total_pages,
            "completed_pages": self.completed_pages,
            "current_batch": self.current_batch,
            "total_batches": self.total_batches,
            "stage": self.stage,
            "error": self.error,
            "progress_percent": self.progress_percent,
            "eta_seconds": self.eta_seconds,
            "elapsed_seconds": self.elapsed_seconds,
        }


class DocumentQueue:
    """文档队列管理器"""

    def __init__(self):
        self._queue: List[DocumentTask] = []
        self._current: Optional[DocumentTask] = None
        self._processing = False
        self._paused = False  # 是否暂停
        self._lock = asyncio.Lock()
        self._subscribers: List[asyncio.Queue] = []  # SSE 订阅者

    def add_task(self, filename: str, file_path: Path) -> DocumentTask:
        """添加任务到队列"""
        task_id = f"{int(time.time() * 1000)}_{filename}"
        task = DocumentTask(
            task_id=task_id,
            filename=filename,
            file_path=file_path,
        )
        self._queue.append(task)
        logger.info("任务已加入队列: %s (队列长度: %d)", filename, len(self._queue))
        self._notify_subscribers()
        return task

    def get_queue_status(self) -> dict:
        """获取队列状态"""
        tasks = []
        
        # 当前任务
        if self._current:
            tasks.append(self._current.to_dict())
        
        # 等待中的任务
        for task in self._queue:
            if task.status == TaskStatus.WAITING:
                tasks.append(task.to_dict())

        return {
            "processing": self._processing,
            "paused": self._paused,
            "current": self._current.to_dict() if self._current else None,
            "queue_length": len([t for t in self._queue if t.status == TaskStatus.WAITING]),
            "tasks": tasks,
        }

    def get_current_progress(self) -> dict:
        """获取当前解析进度（兼容旧接口）"""
        if self._current and self._current.status == TaskStatus.PROCESSING:
            p = self._current.to_dict()
            p["active"] = True
            return p
        return {
            "active": False,
            "filename": "",
            "total_pages": 0,
            "completed_pages": 0,
            "current_batch": 0,
            "total_batches": 0,
            "stage": "",
            "progress_percent": 0,
            "eta_seconds": 0,
            "elapsed_seconds": 0,
        }

    async def subscribe(self) -> asyncio.Queue:
        """订阅进度更新（SSE）"""
        queue = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        """取消订阅"""
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def _notify_subscribers(self):
        """通知所有订阅者"""
        status = self.get_queue_status()
        for queue in self._subscribers:
            try:
                queue.put_nowait(status)
            except asyncio.QueueFull:
                pass  # 忽略满队列

    def update_current_progress(
        self,
        total_pages: int = None,
        completed_pages: int = None,
        current_batch: int = None,
        total_batches: int = None,
        stage: str = None,
        batch_time: float = None,
    ):
        """更新当前任务进度"""
        if not self._current:
            return

        if total_pages is not None:
            self._current.total_pages = total_pages
        if completed_pages is not None:
            self._current.completed_pages = completed_pages
        if current_batch is not None:
            self._current.current_batch = current_batch
        if total_batches is not None:
            self._current.total_batches = total_batches
        if stage is not None:
            self._current.stage = stage
        if batch_time is not None:
            self._current.batch_times.append(batch_time)

        self._notify_subscribers()

    def start_task(self, task: DocumentTask):
        """开始处理任务"""
        task.status = TaskStatus.PROCESSING
        task.start_time = time.time()
        task.stage = "rendering"
        self._current = task
        self._processing = True
        logger.info("开始处理: %s", task.filename)
        self._notify_subscribers()

    def complete_task(self, task: DocumentTask):
        """任务完成"""
        task.status = TaskStatus.COMPLETED
        task.end_time = time.time()
        task.completed_pages = task.total_pages
        task.stage = "done"
        self._current = None
        self._processing = False
        logger.info("任务完成: %s (%.1f秒)", task.filename, task.elapsed_seconds)
        self._notify_subscribers()

    def fail_task(self, task: DocumentTask, error: str):
        """任务失败"""
        task.status = TaskStatus.FAILED
        task.end_time = time.time()
        task.error = error
        self._current = None
        self._processing = False
        logger.error("任务失败: %s - %s", task.filename, error)
        self._notify_subscribers()

    def pause(self):
        """暂停处理"""
        self._paused = True
        if self._current:
            self._current.stage = "已暂停"
        logger.info("队列已暂停")
        self._notify_subscribers()

    def resume(self):
        """继续处理"""
        self._paused = False
        if self._current:
            self._current.stage = "ocr"
        logger.info("队列已继续")
        self._notify_subscribers()

    @property
    def is_paused(self) -> bool:
        return self._paused

    def get_next_task(self) -> Optional[DocumentTask]:
        """获取下一个待处理的任务"""
        for task in self._queue:
            if task.status == TaskStatus.WAITING:
                return task
        return None

    def remove_task(self, task_id: str):
        """移除任务"""
        self._queue = [t for t in self._queue if t.task_id != task_id]
        self._notify_subscribers()

    def clear_completed(self):
        """清理已完成的任务"""
        self._queue = [t for t in self._queue if t.status != TaskStatus.COMPLETED]
        self._notify_subscribers()


# 全局队列实例
document_queue = DocumentQueue()