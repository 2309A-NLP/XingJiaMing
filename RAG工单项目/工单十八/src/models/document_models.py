from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SensitiveMatch(BaseModel):
    """单条敏感信息命中记录。"""

    match_type: str
    raw_value: str
    masked_value: str
    context: str
    file_name: str
    file_path: str


class PDFClassificationResult(BaseModel):
    """PDF 类型识别结果。"""

    document_type: str
    page_char_counts: list[int] = Field(default_factory=list)
    scan_page_ratio: float = 0.0
    pending_confirmation: dict[str, Any] | None = None


class TextExtractionResult(BaseModel):
    """统一文本抽取结果。"""

    text: str = ""
    pdf_classification: PDFClassificationResult | None = None
    errors: list[dict[str, str]] = Field(default_factory=list)


class CollectedDocument(BaseModel):
    """待分析的文档对象。"""

    file_name: str
    file_path: str
    extension: str
    size_bytes: int
    extracted_text: str = ""
    char_count: int = 0
    pdf_type: str | None = None
    page_char_counts: list[int] = Field(default_factory=list)
    pending_confirmation: dict[str, Any] | None = None
    labels: list[str] = Field(default_factory=list)
    parser_decision: dict[str, Any] | None = None
    ocr_text: str = ""
    ocr_page_results: list[dict[str, Any]] = Field(default_factory=list)
    ocr_layout_summary: dict[str, Any] = Field(default_factory=dict)
    md5_hash: str | None = None
    sensitive_matches: list[SensitiveMatch] = Field(default_factory=list)

    @property
    def path(self) -> Path:
        """返回 Path 形式，内部处理更方便。"""

        return Path(self.file_path)
