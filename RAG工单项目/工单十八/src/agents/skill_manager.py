from __future__ import annotations

from src.agents.registry import SkillRegistry
from src.agents.skills.document_quality_assessment import DocumentQualityAssessmentSkill
from src.core.settings import get_settings
from src.models.api_models import QualityInspectionRequest
from src.models.report_models import InspectionExecutionResult


class SkillManager:
    """统一管理技能注册和执行。"""

    def __init__(self):
        settings = get_settings()
        self.registry = SkillRegistry(settings.skill_root_dir)
        self.runners = {
            "document-quality-assessment": DocumentQualityAssessmentSkill(),
        }

    def run(self, skill_name: str, request: QualityInspectionRequest) -> InspectionExecutionResult:
        """执行指定技能。"""

        runner = self.runners[skill_name]
        return runner.run(request)


def build_skill_manager() -> SkillManager:
    """构建技能管理器。"""

    return SkillManager()

