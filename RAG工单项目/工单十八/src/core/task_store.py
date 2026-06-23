from __future__ import annotations

import time
import uuid
from pathlib import Path

from src.core.settings import Settings, get_settings
from src.models.task_models import InspectionTaskState


class TaskStore:
    """把任务状态持久化到 storage/tasks。"""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def create(self, request_payload: dict) -> InspectionTaskState:
        """创建新任务。"""

        task = InspectionTaskState(
            task_id=uuid.uuid4().hex,
            status="pending",
            progress=0,
            current_step="pending",
            request_payload=request_payload,
            started_at=time.time(),
        )
        self.save(task)
        return task

    def save(self, task: InspectionTaskState) -> None:
        """保存任务文件。"""

        path = self._build_path(task.task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(task.model_dump_json(indent=2), encoding="utf-8")

    def load(self, task_id: str) -> InspectionTaskState | None:
        """读取任务状态。"""

        path = self._build_path(task_id)
        if not path.exists():
            return None
        return InspectionTaskState.model_validate_json(path.read_text(encoding="utf-8"))

    def _build_path(self, task_id: str) -> Path:
        """统一任务状态文件路径。"""

        return self.settings.task_state_dir / f"{task_id}.json"
