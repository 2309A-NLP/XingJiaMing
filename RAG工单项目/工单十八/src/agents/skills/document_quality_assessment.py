from __future__ import annotations

from src.models.api_models import QualityInspectionRequest
from src.models.report_models import InspectionExecutionResult
from src.pipeline.quality_assessment_service import QualityAssessmentService


class DocumentQualityAssessmentSkill:
    """把技能调用映射到质检服务。"""

    def __init__(self):
        self.service = QualityAssessmentService()

    def run(self, request: QualityInspectionRequest) -> InspectionExecutionResult:
        """执行技能。"""

        return self.service.inspect(request)

