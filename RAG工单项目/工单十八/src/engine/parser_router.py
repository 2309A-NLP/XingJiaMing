from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Protocol

from src.core.exceptions import OCRUnavailableError
from src.core.settings import get_settings
from src.models.document_models import CollectedDocument


class OCRBackend(Protocol):
    """统一 OCR 后端协议。"""

    def ensure_available(self) -> None:
        ...

    def extract_from_pdf(self, pdf_path: str | Path) -> dict[str, Any]:
        ...


def route_document_parser(
    document: CollectedDocument,
    ocr_config: dict[str, Any] | None = None,
    ocr_backend_factory: Callable[[str], OCRBackend] | None = None,
) -> dict[str, Any]:
    """根据文档类型决定走文本解析还是 OCR。"""

    settings = get_settings()
    effective_ocr_config = ocr_config or {}
    execution_enabled = bool(effective_ocr_config.get("execution_enabled", False))
    return_error_decision = bool(effective_ocr_config.get("return_error_decision", True))

    if document.pdf_type not in {"scan_pdf", "mixed_pdf"}:
        decision = {
            "parser_type": "text",
            "provider": "builtin",
            "execution_mode": "builtin",
            "execution_status": "completed",
        }
        document.parser_decision = decision
        return decision

    decision: dict[str, Any] = {
        "parser_type": "ocr",
        "provider": settings.ocr_provider,
        "execution_mode": "route_only",
        "execution_status": "pending",
        "reason": "检测到扫描型或混合型 PDF，建议路由到 OCR 解析器。",
    }

    if not execution_enabled:
        document.parser_decision = decision
        return decision

    try:
        backend = (ocr_backend_factory or build_ocr_backend)(settings.ocr_provider)
        backend.ensure_available()
        result = backend.extract_from_pdf(document.file_path)
    except OCRUnavailableError as error:
        if not return_error_decision:
            raise
        decision.update(
            {
                "execution_mode": "executed",
                "execution_status": "failed",
                "error_message": str(error),
            }
        )
        document.parser_decision = decision
        return decision
    except Exception as error:
        if not return_error_decision:
            raise OCRUnavailableError(f"OCR 执行异常: {error.__class__.__name__}: {error}") from error
        decision.update(
            {
                "execution_mode": "executed",
                "execution_status": "failed",
                "error_message": f"OCR 执行异常: {error.__class__.__name__}: {error}",
            }
        )
        document.parser_decision = decision
        return decision

    document.ocr_text = result.get("text", "")
    document.ocr_page_results = result.get("page_results", [])
    document.ocr_layout_summary = result.get("layout_summary", {})
    decision.update(
        {
            "provider": result.get("provider", settings.ocr_provider),
            "execution_mode": "executed",
            "execution_status": "completed",
            "ocr_text": document.ocr_text,
            "ocr_text_char_count": len(document.ocr_text.strip()),
            "page_results": document.ocr_page_results,
            "layout_summary": document.ocr_layout_summary,
        }
    )
    document.parser_decision = decision
    return decision


def build_ocr_backend(provider: str) -> OCRBackend:
    """按配置返回对应 OCR 后端。"""

    from src.engine.ocr_backends import AutoOCRBackend, HybridOCRBackend, MinerUBackend, PaddleOCRBackend

    if provider == "paddleocr":
        return PaddleOCRBackend()
    if provider == "mineru":
        return MinerUBackend()
    if provider == "hybrid":
        return HybridOCRBackend()
    if provider == "auto":
        return AutoOCRBackend()
    raise OCRUnavailableError("OCR_PROVIDER 配置无效，请使用 auto、paddleocr、mineru 或 hybrid")
