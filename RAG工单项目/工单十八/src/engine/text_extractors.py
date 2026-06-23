from __future__ import annotations

from pathlib import Path

from docx import Document
from pypdf import PdfReader

from src.core.exceptions import DocumentReadError
from src.models.document_models import TextExtractionResult
from src.pipeline.pdf_page_classifier import classify_pdf_document


def extract_document_text(path: str | Path, config: dict) -> TextExtractionResult:
    """根据后缀抽取文本。"""

    path_obj = Path(path)
    suffix = path_obj.suffix.lower()
    try:
        if suffix in {".md", ".txt"}:
            return TextExtractionResult(text=path_obj.read_text(encoding="utf-8"))
        if suffix == ".docx":
            document = Document(path_obj)
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
            return TextExtractionResult(text=text)
        if suffix == ".pdf":
            reader = PdfReader(str(path_obj))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            classification = classify_pdf_document(path_obj, config)
            return TextExtractionResult(text=text, pdf_classification=classification)
    except Exception as error:
        raise DocumentReadError(f"读取文档失败: {path_obj.name}") from error
    raise DocumentReadError(f"暂不支持的文件类型: {path_obj.suffix}")
