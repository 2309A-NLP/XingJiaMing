from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from src.core.settings import get_settings
from src.models.document_models import PDFClassificationResult


def classify_pdf_document(pdf_path: str | Path, config: dict | None = None) -> PDFClassificationResult:
    """按页字符数做 PDF 类型启发式判断。"""

    settings = get_settings()
    assessment_config = config or settings.load_assessment_config()
    pdf_config = assessment_config.get("pdf", {})
    page_threshold = int(pdf_config.get("scan_page_char_threshold", 8))
    scan_ratio_threshold = float(pdf_config.get("scan_ratio_threshold", 0.7))
    text_ratio_threshold = float(pdf_config.get("text_ratio_threshold", 0.3))
    pending_margin = float(pdf_config.get("pending_confirmation_margin", 0.1))

    reader = PdfReader(str(pdf_path))
    page_char_counts: list[int] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        page_char_counts.append(len(text.strip()))

    total_pages = max(len(page_char_counts), 1)
    scan_pages = sum(1 for count in page_char_counts if count < page_threshold)
    scan_ratio = scan_pages / total_pages
    pending_confirmation = None

    if scan_ratio >= scan_ratio_threshold:
        document_type = "scan_pdf"
    elif scan_ratio <= text_ratio_threshold:
        document_type = "text_pdf"
    else:
        document_type = "mixed_pdf"

    if abs(scan_ratio - scan_ratio_threshold) <= pending_margin or abs(scan_ratio - text_ratio_threshold) <= pending_margin:
        pending_confirmation = {
            "file_name": Path(pdf_path).name,
            "reason": "扫描页占比接近阈值，建议人工确认",
            "scan_page_ratio": round(scan_ratio, 4),
            "page_char_counts": page_char_counts,
        }

    return PDFClassificationResult(
        document_type=document_type,
        page_char_counts=page_char_counts,
        scan_page_ratio=round(scan_ratio, 4),
        pending_confirmation=pending_confirmation,
    )

