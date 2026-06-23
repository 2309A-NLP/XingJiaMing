from __future__ import annotations

from pathlib import Path

from scripts.run_imdr_validation import (
    _build_parser,
    _build_validation_request,
    _count_questions,
    _sample_documents,
)


def test_sample_documents_returns_supported_files_only(sample_documents):
    folder = sample_documents["folder"]

    result = _sample_documents(Path(folder), limit=10)

    assert result
    assert all(Path(path).suffix.lower() in {".pdf", ".docx", ".md", ".txt"} for path in result)


def test_count_questions_returns_zero_for_missing_file(tmp_path: Path):
    result = _count_questions(tmp_path / "missing.jsonl")

    assert result == 0


def test_build_parser_accepts_enable_ocr_execution_flag():
    parser = _build_parser()

    args = parser.parse_args(["--enable-ocr-execution"])

    assert args.enable_ocr_execution is True


def test_build_validation_request_can_enable_ocr_execution(sample_documents):
    request = _build_validation_request(
        [str(sample_documents["scan_pdf"])],
        enable_ocr_execution=True,
    )

    assert request.file_paths == [str(sample_documents["scan_pdf"])]
    assert request.mode == "sync"
    assert request.include_html_content is False
    assert request.config_overrides == {"ocr": {"execution_enabled": True}}
