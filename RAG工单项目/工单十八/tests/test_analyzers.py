from __future__ import annotations

from pathlib import Path

from src.engine.parser_router import route_document_parser
from src.core.exceptions import OCRUnavailableError
from src.models.api_models import QualityInspectionRequest
from src.models.document_models import CollectedDocument
from src.pipeline.dedup_analyzer import analyze_duplicates
from src.pipeline.pdf_page_classifier import classify_pdf_document
from src.pipeline.quality_assessment_service import QualityAssessmentService


def test_pdf_page_classifier_marks_text_scan_and_mixed(sample_documents):
    text_result = classify_pdf_document(sample_documents["text_pdf"])
    scan_result = classify_pdf_document(sample_documents["scan_pdf"])
    mixed_result = classify_pdf_document(sample_documents["mixed_pdf"])

    assert text_result.document_type == "text_pdf"
    assert scan_result.document_type == "scan_pdf"
    assert mixed_result.document_type == "mixed_pdf"


def test_quality_service_builds_required_report_sections(sample_documents):
    request = QualityInspectionRequest(
        file_paths=[
            str(sample_documents["md_one"]),
            str(sample_documents["md_two"]),
            str(sample_documents["txt"]),
            str(sample_documents["docx"]),
            str(sample_documents["text_pdf"]),
        ],
        mode="sync",
        include_html_content=True,
    )

    service = QualityAssessmentService()
    result = service.inspect(request)
    report = result.report

    assert result.status == "completed"
    assert report is not None
    assert report.summary.total_documents == 5
    assert report.format_distribution["pdf"]["count"] == 1
    assert report.format_distribution["md"]["count"] == 2
    assert report.duplicate_summary.exact_duplicate_groups
    assert report.sensitive_info_summary.total_matches >= 2
    assert report.pending_reviews
    assert report.html_report.html_content is not None
    assert "document quality report" in report.html_report.html_content.lower()


def test_simhash_candidates_are_reported_without_affecting_exact_duplicates(sample_documents):
    documents = [
        CollectedDocument(
            file_name=sample_documents["near_dup_one"].name,
            file_path=str(sample_documents["near_dup_one"]),
            extension="md",
            size_bytes=sample_documents["near_dup_one"].stat().st_size,
            extracted_text=sample_documents["near_dup_one"].read_text(encoding="utf-8"),
        ),
        CollectedDocument(
            file_name=sample_documents["near_dup_two"].name,
            file_path=str(sample_documents["near_dup_two"]),
            extension="md",
            size_bytes=sample_documents["near_dup_two"].stat().st_size,
            extracted_text=sample_documents["near_dup_two"].read_text(encoding="utf-8"),
        ),
    ]

    summary = analyze_duplicates(documents, {"enabled": True, "distance_threshold": 12})

    assert summary.exact_duplicate_groups == []
    assert summary.simhash_candidates
    assert {documents[0].file_name, documents[1].file_name} == set(summary.simhash_candidates[0].files)
    assert summary.simhash_candidates[0].left_file == documents[0].file_name
    assert summary.simhash_candidates[0].right_file == documents[1].file_name


def test_route_document_parser_returns_route_only_decision_for_scan_pdf_by_default(sample_documents):
    document = CollectedDocument(
        file_name=sample_documents["scan_pdf"].name,
        file_path=str(sample_documents["scan_pdf"]),
        extension="pdf",
        size_bytes=sample_documents["scan_pdf"].stat().st_size,
        pdf_type="scan_pdf",
    )

    decision = route_document_parser(document)

    assert decision["parser_type"] == "ocr"
    assert decision["execution_mode"] == "route_only"
    assert decision["execution_status"] == "pending"
    assert "OCR" in decision["reason"]


def test_route_document_parser_returns_ocr_result_when_backend_is_injected(sample_documents):
    document = CollectedDocument(
        file_name=sample_documents["scan_pdf"].name,
        file_path=str(sample_documents["scan_pdf"]),
        extension="pdf",
        size_bytes=sample_documents["scan_pdf"].stat().st_size,
        pdf_type="scan_pdf",
    )

    decision = route_document_parser(
        document,
        ocr_config={"execution_enabled": True},
        ocr_backend_factory=lambda provider: _FakeOCRBackend(provider),
    )

    assert decision["parser_type"] == "ocr"
    assert decision["provider"] == "auto"
    assert decision["execution_mode"] == "executed"
    assert decision["execution_status"] == "completed"
    assert decision["ocr_text_char_count"] > 0
    assert decision["page_results"][0]["text"]


def test_route_document_parser_returns_readable_error_when_ocr_execution_fails(sample_documents):
    document = CollectedDocument(
        file_name=sample_documents["scan_pdf"].name,
        file_path=str(sample_documents["scan_pdf"]),
        extension="pdf",
        size_bytes=sample_documents["scan_pdf"].stat().st_size,
        pdf_type="scan_pdf",
    )

    decision = route_document_parser(
        document,
        ocr_config={"execution_enabled": True, "return_error_decision": True},
        ocr_backend_factory=lambda provider: _FailingOCRBackend(provider),
    )

    assert decision["parser_type"] == "ocr"
    assert decision["execution_mode"] == "executed"
    assert decision["execution_status"] == "failed"
    assert "OCR" in decision["error_message"]


def test_route_document_parser_converts_runtime_error_to_failed_decision(sample_documents):
    document = CollectedDocument(
        file_name=sample_documents["scan_pdf"].name,
        file_path=str(sample_documents["scan_pdf"]),
        extension="pdf",
        size_bytes=sample_documents["scan_pdf"].stat().st_size,
        pdf_type="scan_pdf",
    )

    decision = route_document_parser(
        document,
        ocr_config={"execution_enabled": True, "return_error_decision": True},
        ocr_backend_factory=lambda provider: _RuntimeFailingOCRBackend(provider),
    )

    assert decision["parser_type"] == "ocr"
    assert decision["execution_status"] == "failed"
    assert "NotImplementedError" in decision["error_message"]


class _FakeOCRBackend:
    """这里造一个最小 OCR 假实现，专门验证路由逻辑。"""

    def __init__(self, provider: str):
        self.provider = provider

    def ensure_available(self) -> None:
        return None

    def extract_from_pdf(self, pdf_path: str | Path) -> dict:
        return {
            "provider": self.provider,
            "text": "fake ocr text",
            "page_results": [
                {
                    "page_number": 1,
                    "text": "fake ocr text",
                    "layout_regions": [{"category": "table", "score": 0.9}],
                    "vision_description": "sample image description",
                }
            ],
            "layout_summary": {"table": 1},
        }


class _FailingOCRBackend:
    """这里模拟真实 OCR 运行时失败，验证路由信息别丢。"""

    def __init__(self, provider: str):
        self.provider = provider

    def ensure_available(self) -> None:
        return None

    def extract_from_pdf(self, pdf_path: str | Path) -> dict:
        raise OCRUnavailableError("OCR 执行失败，当前环境缺少可用运行时")


class _RuntimeFailingOCRBackend:
    """这里模拟 OCR 底层库直接抛运行时异常。"""

    def __init__(self, provider: str):
        self.provider = provider

    def ensure_available(self) -> None:
        return None

    def extract_from_pdf(self, pdf_path: str | Path) -> dict:
        raise NotImplementedError("runtime backend crashed")
