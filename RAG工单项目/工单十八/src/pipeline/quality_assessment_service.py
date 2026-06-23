from __future__ import annotations

from src.core.exceptions import DocumentReadError, OCRUnavailableError
from src.core.settings import get_settings
from src.engine.parser_router import route_document_parser
from src.engine.text_extractors import extract_document_text
from src.models.api_models import QualityInspectionRequest
from src.models.report_models import InspectionExecutionResult
from src.pipeline.dedup_analyzer import analyze_duplicates
from src.pipeline.document_collector import collect_documents
from src.pipeline.format_stats_analyzer import build_format_distribution
from src.pipeline.html_report_renderer import render_html_report
from src.pipeline.labeling_service import assign_labels
from src.pipeline.length_distribution_analyzer import build_length_distribution
from src.pipeline.report_builder import build_quality_report
from src.pipeline.sensitive_info_analyzer import analyze_sensitive_info


class QualityAssessmentService:
    """封装一次完整的文档质量评估流程。"""

    def __init__(self) -> None:
        self.settings = get_settings()

    def inspect(self, request: QualityInspectionRequest) -> InspectionExecutionResult:
        """同步执行质检。"""

        config = self.settings.load_assessment_config(request.config_overrides)
        documents, errors = collect_documents(request, config)
        pending_confirmations: list[dict] = []
        ocr_config = config.get("ocr", {})

        for document in documents:
            try:
                extraction = extract_document_text(document.file_path, config)
                document.extracted_text = extraction.text
                document.char_count = len(extraction.text.strip())
                if extraction.pdf_classification:
                    document.pdf_type = extraction.pdf_classification.document_type
                    document.page_char_counts = extraction.pdf_classification.page_char_counts
                    if extraction.pdf_classification.pending_confirmation:
                        pending_confirmations.append(extraction.pdf_classification.pending_confirmation)
                        document.pending_confirmation = extraction.pdf_classification.pending_confirmation
            except DocumentReadError as error:
                errors.append({"file_name": document.file_name, "type": "read", "message": str(error)})

        status = "completed"
        current_step = "finish"
        completed_steps = ["collect_inputs", "run_quality_assessment", "assign_labels"]

        for document in documents:
            try:
                decision = route_document_parser(document, ocr_config=ocr_config)
            except OCRUnavailableError as error:
                errors.append({"file_name": document.file_name, "type": "ocr", "message": str(error)})
                if bool(ocr_config.get("fail_on_error", False)):
                    status = "failed"
                    current_step = "route_parser"
                continue

            if decision.get("parser_type") == "ocr" and document.ocr_text.strip():
                document.extracted_text = document.ocr_text
                document.char_count = len(document.ocr_text.strip())

            if decision.get("parser_type") == "ocr" and decision.get("execution_mode") == "route_only":
                pending_confirmations.append(
                    {
                        "file_name": document.file_name,
                        "reason": decision.get("reason", "建议接入 OCR 解析器后再继续处理"),
                        "recommended_parser": decision.get("provider", self.settings.ocr_provider),
                    }
                )

            if decision.get("parser_type") == "ocr" and decision.get("execution_status") == "failed":
                errors.append(
                    {
                        "file_name": document.file_name,
                        "type": "ocr",
                        "message": decision.get("error_message", "OCR 执行失败"),
                    }
                )
                pending_confirmations.append(
                    {
                        "file_name": document.file_name,
                        "reason": decision.get("error_message", "OCR 执行失败，请检查环境依赖"),
                        "recommended_parser": decision.get("provider", self.settings.ocr_provider),
                    }
                )
                if bool(ocr_config.get("fail_on_error", False)):
                    status = "failed"
                    current_step = "route_parser"

        format_distribution = build_format_distribution(documents)
        pdf_type_summary = _build_pdf_type_summary(documents)
        length_distribution = build_length_distribution(documents, config)
        duplicate_summary = analyze_duplicates(documents, config.get("simhash"))
        sensitive_info_summary, pending_reviews = analyze_sensitive_info(documents, config)
        labels = assign_labels(documents, duplicate_summary, config)

        if status == "completed":
            completed_steps.append("route_parser")

        report = build_quality_report(
            documents=documents,
            format_distribution=format_distribution,
            pdf_type_summary=pdf_type_summary,
            length_distribution=length_distribution,
            duplicate_summary=duplicate_summary,
            sensitive_info_summary=sensitive_info_summary,
            labels=labels,
            pending_confirmations=pending_confirmations,
            pending_reviews=pending_reviews,
            errors=errors,
        )
        report.html_report = render_html_report(report, request.include_html_content)

        if status == "completed":
            completed_steps.extend(["generate_reports", "finish"])

        return InspectionExecutionResult(
            status=status,
            progress=100,
            report=report,
            current_step=current_step,
            completed_steps=completed_steps,
            error_message=errors[-1]["message"] if errors and status == "failed" else None,
        )


def _build_pdf_type_summary(documents: list) -> dict:
    """整理 PDF 类型统计。"""

    summary = {
        "text_pdf": {"count": 0},
        "scan_pdf": {"count": 0},
        "mixed_pdf": {"count": 0},
    }
    for document in documents:
        if document.pdf_type in summary:
            summary[document.pdf_type]["count"] += 1
    return summary
