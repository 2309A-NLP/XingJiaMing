from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InspectionTaskState(BaseModel):
    """异步任务状态快照。"""

    task_id: str
    status: str
    progress: int = 0
    current_step: str = "pending"
    completed_steps: list[str] = Field(default_factory=list)
    failed_step: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    request_payload: dict[str, Any] = Field(default_factory=dict)
    report: dict[str, Any] | None = None
    html_path: str | None = None
    html_content: str | None = None
    error_message: str | None = None

