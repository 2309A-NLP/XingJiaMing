from __future__ import annotations

from src.models.document_models import CollectedDocument
from src.models.report_models import (
    DuplicateSummary,
    QualityInspectionReport,
    ReportSummary,
    SensitiveInfoSummary,
)


def build_quality_report(
    documents: list[CollectedDocument],
    format_distribution: dict,
    pdf_type_summary: dict,
    length_distribution: dict,
    duplicate_summary: DuplicateSummary,
    sensitive_info_summary: SensitiveInfoSummary,
    labels: dict[str, list[str]],
    pending_confirmations: list[dict],
    pending_reviews: list[dict],
    errors: list[dict],
) -> QualityInspectionReport:
    """把各阶段结果拼成统一报告。"""

    routing_decisions = {document.file_name: document.parser_decision or {} for document in documents}
    summary = ReportSummary(
        total_documents=len(documents),
        supported_documents=len(documents),
        exact_duplicate_groups=len(duplicate_summary.exact_duplicate_groups),
        simhash_candidate_groups=len(duplicate_summary.simhash_candidates),
        sensitive_documents=sum(1 for document in documents if document.sensitive_matches),
        failed_documents=len(errors),
        routing_decisions=routing_decisions,
    )
    return QualityInspectionReport(
        summary=summary,
        format_distribution=format_distribution,
        pdf_type_summary=pdf_type_summary,
        length_distribution=length_distribution,
        duplicate_summary=duplicate_summary,
        sensitive_info_summary=sensitive_info_summary,
        document_labels=labels,
        pending_confirmations=pending_confirmations,
        pending_reviews=pending_reviews,
        errors=errors,
    )
