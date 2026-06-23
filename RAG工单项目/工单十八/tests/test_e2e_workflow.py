from __future__ import annotations

from unittest.mock import patch
from src.models.api_models import QualityInspectionRequest
from src.pipeline.quality_assessment_service import QualityAssessmentService


def test_e2e_report_contains_labels_duplicates_and_routing(sample_documents):
    service = QualityAssessmentService()
    request = QualityInspectionRequest(
        folder_path=str(sample_documents["folder"]),
        mode="sync",
        include_html_content=True,
    )

    result = service.inspect(request)
    report = result.report

    assert result.status == "completed"
    assert report is not None
    assert report.summary.total_documents == 7
    assert "duplicate_exact" in report.document_labels["policy.md"]
    assert "sensitive_review_required" in report.document_labels["policy.md"]
    assert report.summary.routing_decisions["text.pdf"]["parser_type"] == "text"
    assert report.summary.routing_decisions["scan.pdf"]["parser_type"] == "ocr"
    assert report.summary.routing_decisions["scan.pdf"]["execution_mode"] == "route_only"
    assert report.pending_confirmations


def test_e2e_report_keeps_broken_pdf_error_without_stopping_batch(sample_documents):
    service = QualityAssessmentService()
    request = QualityInspectionRequest(
        file_paths=[
            str(sample_documents["text_pdf"]),
            str(sample_documents["broken_pdf"]),
            str(sample_documents["near_dup_one"]),
            str(sample_documents["near_dup_two"]),
        ],
        mode="sync",
        include_html_content=False,
        config_overrides={"simhash": {"enabled": True, "distance_threshold": 12}},
    )

    result = service.inspect(request)
    report = result.report

    assert report is not None
    assert report.summary.total_documents == 4
    assert any(item["type"] == "read" for item in report.errors)
    assert report.duplicate_summary.simhash_candidates
    assert report.summary.routing_decisions["text.pdf"]["parser_type"] == "text"


def test_e2e_report_keeps_route_decision_when_ocr_execution_fails(sample_documents):
    service = QualityAssessmentService()
    request = QualityInspectionRequest(
        file_paths=[str(sample_documents["scan_pdf"])],
        mode="sync",
        include_html_content=False,
        config_overrides={
            "ocr": {
                "execution_enabled": True,
                "fail_on_error": False,
            }
        },
    )

    with patch(
        "src.pipeline.quality_assessment_service.route_document_parser",
        side_effect=_mock_failed_ocr_route,
    ):
        result = service.inspect(request)
    report = result.report

    assert result.status == "completed"
    assert report is not None
    assert report.summary.routing_decisions["scan.pdf"]["parser_type"] == "ocr"
    assert report.summary.routing_decisions["scan.pdf"]["execution_status"] == "failed"
    assert report.errors


def _mock_failed_ocr_route(document, ocr_config=None):
    document.parser_decision = {
        "parser_type": "ocr",
        "provider": "auto",
        "execution_mode": "executed",
        "execution_status": "failed",
        "error_message": "OCR 执行异常: NotImplementedError: runtime backend crashed",
    }
    return document.parser_decision
