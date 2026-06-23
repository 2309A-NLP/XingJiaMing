from __future__ import annotations

from src.agents.skill_manager import build_skill_manager
from src.models.api_models import QualityInspectionRequest


def test_skill_manager_discovers_and_executes_document_quality_assessment(sample_documents):
    manager = build_skill_manager()
    request = QualityInspectionRequest(
        file_paths=[str(sample_documents["txt"])],
        mode="sync",
        include_html_content=False,
    )

    registry = manager.registry
    metadata = registry.get("document-quality-assessment")
    result = manager.run("document-quality-assessment", request)

    assert metadata.name == "document-quality-assessment"
    assert "quality" in metadata.description.lower()
    assert result.status == "completed"
    assert result.report is not None


def test_skill_manager_supports_simhash_config_override(sample_documents):
    manager = build_skill_manager()
    request = QualityInspectionRequest(
        file_paths=[
            str(sample_documents["near_dup_one"]),
            str(sample_documents["near_dup_two"]),
        ],
        mode="sync",
        include_html_content=False,
        config_overrides={"simhash": {"enabled": True, "distance_threshold": 12}},
    )

    result = manager.run("document-quality-assessment", request)

    assert result.status == "completed"
    assert result.report is not None
    assert result.report.duplicate_summary.simhash_candidates
