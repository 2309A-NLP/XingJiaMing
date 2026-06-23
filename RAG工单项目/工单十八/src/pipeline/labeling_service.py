from __future__ import annotations

from src.models.document_models import CollectedDocument
from src.models.report_models import DuplicateSummary


def assign_labels(documents: list[CollectedDocument], duplicate_summary: DuplicateSummary, config: dict) -> dict[str, list[str]]:
    """把质检结果映射成统一标签。"""

    low_text_threshold = int(config.get("length_distribution", {}).get("low_text_threshold", 20))
    duplicate_files = {
        file_name
        for group in duplicate_summary.exact_duplicate_groups
        for file_name in group.files
    }
    labels_by_document: dict[str, list[str]] = {}

    for document in documents:
        labels: list[str] = []
        if document.pdf_type in {"scan_pdf", "text_pdf", "mixed_pdf"}:
            labels.append(document.pdf_type)
        if document.file_name in duplicate_files:
            labels.append("duplicate_exact")
        if document.sensitive_matches:
            labels.append("sensitive_review_required")
        if document.char_count < low_text_threshold:
            labels.append("low_text_content")
        document.labels = labels
        labels_by_document[document.file_name] = labels
    return labels_by_document

