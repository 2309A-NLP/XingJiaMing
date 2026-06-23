from __future__ import annotations

import json
from pathlib import Path

import pytest
from docx import Document
from reportlab.pdfgen import canvas


def _write_text(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def _write_docx(path: Path, content: str) -> Path:
    doc = Document()
    doc.add_paragraph(content)
    doc.save(path)
    return path


def _write_pdf(path: Path, pages: list[str]) -> Path:
    pdf = canvas.Canvas(str(path))
    for text in pages:
        if text:
            pdf.drawString(72, 720, text)
        pdf.showPage()
    pdf.save()
    return path


def _write_binary(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


@pytest.fixture()
def sample_documents(tmp_path: Path) -> dict[str, Path]:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    extra_dir = tmp_path / "extra_docs"
    extra_dir.mkdir()

    md_one = _write_text(
        docs_dir / "policy.md",
        "联系人：13800138000\n邮箱：admin@example.com\n这是一份知识库文档。",
    )
    md_two = _write_text(
        docs_dir / "policy_copy.md",
        "联系人：13800138000\n邮箱：admin@example.com\n这是一份知识库文档。",
    )
    txt_file = _write_text(docs_dir / "notes.txt", "普通文本内容，用于长度统计。")
    docx_file = _write_docx(docs_dir / "guide.docx", "这是 docx 文档内容。")
    text_pdf = _write_pdf(docs_dir / "text.pdf", ["This page has enough plain text content for classification."])
    scan_pdf = _write_pdf(docs_dir / "scan.pdf", [""])
    mixed_pdf = _write_pdf(docs_dir / "mixed.pdf", ["This page is text and should be treated as a text page.", ""])
    near_dup_one = _write_text(extra_dir / "near_duplicate_one.md", "Product guide for OCR workflow with routing decisions and document quality checks.")
    near_dup_two = _write_text(extra_dir / "near_duplicate_two.md", "Product guide for OCR workflows with routing decision and document quality check.")
    broken_pdf = _write_binary(extra_dir / "broken.pdf", b"not-a-real-pdf")
    questions_jsonl = extra_dir / "questions.jsonl"
    questions_jsonl.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "question": "What is the sample text PDF about?",
                        "document": "text.pdf",
                        "options": ["A. OCR", "B. Tables", "C. Images", "D. Audio"],
                        "answer": "A",
                        "group": 1,
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "question": "Which file is a scan example?",
                        "document": "scan.pdf",
                        "options": ["A. text.pdf", "B. scan.pdf", "C. notes.txt", "D. guide.docx"],
                        "answer": "B",
                        "group": 1,
                    },
                    ensure_ascii=False,
                ),
            ]
        ),
        encoding="utf-8",
    )

    return {
        "folder": docs_dir,
        "md_one": md_one,
        "md_two": md_two,
        "txt": txt_file,
        "docx": docx_file,
        "text_pdf": text_pdf,
        "scan_pdf": scan_pdf,
        "mixed_pdf": mixed_pdf,
        "near_dup_one": near_dup_one,
        "near_dup_two": near_dup_two,
        "broken_pdf": broken_pdf,
        "questions_jsonl": questions_jsonl,
    }
