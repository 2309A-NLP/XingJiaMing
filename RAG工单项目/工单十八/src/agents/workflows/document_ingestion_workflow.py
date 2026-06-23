from __future__ import annotations

import time

from src.models.api_models import QualityInspectionRequest
from src.models.report_models import InspectionExecutionResult
from src.models.task_models import InspectionTaskState
from src.pipeline.quality_assessment_service import QualityAssessmentService


class DocumentIngestionWorkflow:
    """顺序式工作流。"""

    def __init__(self):
        self.service = QualityAssessmentService()

    def run(self, request: QualityInspectionRequest, task: InspectionTaskState | None = None) -> InspectionExecutionResult:
        """执行顺序流程。"""

        result = self.service.inspect(request)
        if task is not None:
            task.status = result.status
            task.progress = result.progress
            task.current_step = result.current_step
            task.completed_steps = result.completed_steps
            task.finished_at = time.time()
            task.report = result.report.model_dump() if result.report else None
            task.error_message = result.error_message
            if result.report:
                task.html_path = result.report.html_report.html_path
                task.html_content = result.report.html_report.html_content
        return result

