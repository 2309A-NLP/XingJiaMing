from __future__ import annotations

import json
import sys
import types
from pathlib import Path

from PIL import Image

from src.engine.ocr_backends import MinerUBackend, PaddleOCRBackend
from src.engine.vision_analyzer import VisionAnalyzer


def test_vision_analyzer_skips_uniform_images() -> None:
    analyzer = VisionAnalyzer()
    blank_image = Image.new("RGB", (16, 16), color="white")

    assert analyzer.should_analyze(blank_image) is False


def test_paddleocr_backend_adds_vision_description_for_short_pages(monkeypatch, tmp_path: Path) -> None:
    _install_fake_ocr_modules(monkeypatch)
    backend = PaddleOCRBackend()
    backend.settings = backend.settings.model_copy(update={"ocr_command": "inline"})
    backend.vision_analyzer = _FakeVisionAnalyzer()

    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    result = backend.extract_from_pdf(pdf_path)

    assert result["provider"] == "paddleocr"
    assert result["page_results"][0]["vision_description"] == "图片说明"


def test_mineru_backend_parses_layout_json_when_cli_succeeds(monkeypatch, tmp_path: Path) -> None:
    fake_magic_pdf = types.ModuleType("magic_pdf")
    fake_tools = types.ModuleType("magic_pdf.tools")
    fake_cli = types.ModuleType("magic_pdf.tools.cli")
    fake_magic_pdf.tools = fake_tools
    fake_tools.cli = fake_cli
    monkeypatch.setitem(sys.modules, "magic_pdf", fake_magic_pdf)
    monkeypatch.setitem(sys.modules, "magic_pdf.tools", fake_tools)
    monkeypatch.setitem(sys.modules, "magic_pdf.tools.cli", fake_cli)

    def fake_run(cmd, capture_output, text, timeout, **kwargs):
        output_dir = Path(cmd[cmd.index("-o") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        layout_payload = {
            "page_no": 1,
            "layout_dets": [
                {"bbox": [1, 2, 3, 4], "category": "table", "score": 0.9},
            ],
        }
        (output_dir / "layout.json").write_text(json.dumps(layout_payload), encoding="utf-8")
        return types.SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("src.engine.ocr_backends.subprocess.run", fake_run)

    backend = MinerUBackend(output_dir=tmp_path)
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    result = backend.extract_from_pdf(pdf_path)

    assert result["provider"] == "mineru"
    assert result["layout_summary"]["json_files"] == 1
    assert result["page_results"][0]["layout_regions"][0]["category"] == "table"


def test_paddleocr_backend_uses_subprocess_when_enabled(monkeypatch, tmp_path: Path) -> None:
    backend = PaddleOCRBackend()
    backend.settings = backend.settings.model_copy(update={"ocr_command": "subprocess"})

    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    def fake_run(cmd, capture_output, text, timeout, **kwargs):
        payload = {
            "provider": "paddleocr",
            "text": "subprocess ocr text",
            "page_results": [{"page_number": 1, "text": "subprocess ocr text", "layout_regions": [], "vision_description": None}],
            "layout_summary": {"mode": "subprocess"},
        }
        return types.SimpleNamespace(returncode=0, stderr="", stdout=json.dumps(payload, ensure_ascii=False))

    monkeypatch.setattr("src.engine.ocr_backends.subprocess.run", fake_run)
    monkeypatch.setattr(backend, "ensure_available", lambda: None)

    result = backend.extract_from_pdf(pdf_path)

    assert result["text"] == "subprocess ocr text"
    assert result["layout_summary"]["mode"] == "subprocess"


def test_paddleocr_backend_returns_readable_error_when_subprocess_fails(monkeypatch, tmp_path: Path) -> None:
    backend = PaddleOCRBackend()
    backend.settings = backend.settings.model_copy(update={"ocr_command": "subprocess"})

    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    def fake_run(cmd, capture_output, text, timeout, **kwargs):
        return types.SimpleNamespace(returncode=1, stderr="backend crashed", stdout="")

    monkeypatch.setattr("src.engine.ocr_backends.subprocess.run", fake_run)
    monkeypatch.setattr(backend, "ensure_available", lambda: None)

    try:
        backend.extract_from_pdf(pdf_path)
    except Exception as error:
        assert "PaddleOCR 子进程执行失败" in str(error)
    else:
        raise AssertionError("expected OCR failure")


class _FakeArray:
    def reshape(self, *shape):
        return self


class _FakePaddleOCR:
    def __init__(self, lang: str = "ch") -> None:
        self.lang = lang

    def ocr(self, image_array):
        return [[[None, ("短文本", 0.99)]]]


class _FakePixmap:
    samples = b"\xff\xff\xff" * 4
    height = 1
    width = 1
    n = 3


class _FakePage:
    def get_pixmap(self, matrix=None, alpha=False):
        return _FakePixmap()


class _FakePdf:
    page_count = 1

    def load_page(self, page_index: int):
        return _FakePage()

    def close(self) -> None:
        return None


class _FakeVisionAnalyzer:
    is_available = True

    def should_analyze(self, image) -> bool:
        return True

    def describe(self, image_payload) -> str:
        return "图片说明"


def _install_fake_ocr_modules(monkeypatch) -> None:
    fake_numpy = types.ModuleType("numpy")
    fake_numpy.uint8 = "uint8"
    fake_numpy.frombuffer = lambda *args, **kwargs: _FakeArray()

    fake_fitz = types.ModuleType("fitz")
    fake_fitz.Matrix = lambda *args, **kwargs: None
    fake_fitz.open = lambda path: _FakePdf()

    fake_paddleocr = types.ModuleType("paddleocr")
    fake_paddleocr.PaddleOCR = _FakePaddleOCR

    monkeypatch.setitem(sys.modules, "numpy", fake_numpy)
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)
    monkeypatch.setitem(sys.modules, "paddleocr", fake_paddleocr)
