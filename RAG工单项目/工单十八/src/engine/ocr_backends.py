from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.core.exceptions import OCRUnavailableError
from src.core.settings import get_settings
from src.engine.vision_analyzer import VisionAnalyzer


class BaseOCRBackend:
    """OCR 后端基类。"""

    provider_name = "base"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.vision_analyzer = VisionAnalyzer()

    def ensure_available(self) -> None:
        raise NotImplementedError

    def extract_from_pdf(self, pdf_path: str | Path) -> dict[str, Any]:
        raise NotImplementedError


class PaddleOCRBackend(BaseOCRBackend):
    """PaddleOCR 文字识别后端。"""

    provider_name = "paddleocr"

    def ensure_available(self) -> None:
        try:
            __import__("fitz")
            __import__("numpy")
            __import__("paddleocr")
        except ImportError as error:
            raise OCRUnavailableError(
                "PaddleOCR 依赖未安装，请先在 .venv 中安装 numpy、paddleocr 和 PyMuPDF"
            ) from error

    def extract_from_pdf(self, pdf_path: str | Path) -> dict[str, Any]:
        if self._use_subprocess_mode():
            return self._extract_with_subprocess(pdf_path)
        return self._extract_inline(pdf_path)

    def _use_subprocess_mode(self) -> bool:
        return (self.settings.ocr_command or "").strip().lower() == "subprocess"

    def _extract_inline(self, pdf_path: str | Path) -> dict[str, Any]:
        self.ensure_available()
        import fitz
        import numpy as np
        from PIL import Image
        from paddleocr import PaddleOCR

        reader = fitz.open(str(pdf_path))
        ocr = PaddleOCR(lang=self.settings.paddleocr_lang)
        page_results: list[dict[str, Any]] = []
        full_text_parts: list[str] = []

        for page_index in range(reader.page_count):
            page = reader.load_page(page_index)
            pix = page.get_pixmap(
                matrix=fitz.Matrix(self.settings.ocr_render_scale, self.settings.ocr_render_scale),
                alpha=False,
            )
            image_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            ocr_result = ocr.ocr(image_array)

            page_lines: list[str] = []
            for block in ocr_result or []:
                if not isinstance(block, list):
                    continue
                for line in block:
                    if isinstance(line, list) and len(line) >= 2:
                        text_info = line[1]
                        if isinstance(text_info, (list, tuple)) and text_info:
                            text = str(text_info[0]).strip()
                            if text:
                                page_lines.append(text)

            page_text = "\n".join(page_lines)
            vision_description = self._maybe_describe_image(image, page_text)
            full_text_parts.extend(part for part in [page_text, vision_description] if part)
            page_results.append(
                {
                    "page_number": page_index + 1,
                    "text": page_text,
                    "layout_regions": [],
                    "vision_description": vision_description,
                }
            )

        reader.close()
        return {
            "provider": self.provider_name,
            "text": "\n".join(full_text_parts),
            "page_results": page_results,
            "layout_summary": {"mode": "inline"},
        }

    def _extract_with_subprocess(self, pdf_path: str | Path) -> dict[str, Any]:
        payload = {
            "pdf_path": str(Path(pdf_path).resolve()),
            "lang": self.settings.paddleocr_lang,
            "render_scale": self.settings.ocr_render_scale,
            "vision_char_threshold": self.settings.ocr_vision_char_threshold,
        }
        cmd = [
            sys.executable,
            "-m",
            "src.engine.paddleocr_worker",
            json.dumps(payload, ensure_ascii=False),
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.settings.ocr_timeout_seconds,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise OCRUnavailableError(f"PaddleOCR 子进程执行失败，请检查运行时环境。错误信息: {stderr[:300]}")
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise OCRUnavailableError("PaddleOCR 子进程输出不是合法 JSON，无法解析结果") from error
        return data

    def _maybe_describe_image(self, image: Any, page_text: str) -> str | None:
        if len(page_text.strip()) >= self.settings.ocr_vision_char_threshold:
            return None
        if not self.vision_analyzer.should_analyze(image):
            return None
        return self.vision_analyzer.describe(image)


class MinerUBackend(BaseOCRBackend):
    """MinerU 布局分析后端。"""

    provider_name = "mineru"

    def __init__(self, output_dir: str | Path | None = None) -> None:
        super().__init__()
        self.output_dir = Path(output_dir or self.settings.mineru_output_dir)

    def ensure_available(self) -> None:
        try:
            __import__("magic_pdf.tools.cli")
        except ImportError as error:
            raise OCRUnavailableError("MinerU 依赖未安装，请先在 .venv 中安装 magic-pdf") from error

    def extract_from_pdf(self, pdf_path: str | Path) -> dict[str, Any]:
        self.ensure_available()
        pdf_path = Path(pdf_path)
        output_dir = self.output_dir / pdf_path.stem
        output_dir.mkdir(parents=True, exist_ok=True)
        cmd = self._build_command(pdf_path, output_dir)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.settings.ocr_timeout_seconds,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise OCRUnavailableError(f"MinerU 执行失败，请检查 CLI 和模型配置。错误信息: {stderr[:300]}")

        regions_by_page = self.get_layout_regions(output_dir)
        page_results = [
            {
                "page_number": page_no,
                "text": "",
                "layout_regions": regions,
                "vision_description": None,
            }
            for page_no, regions in sorted(regions_by_page.items())
        ]
        return {
            "provider": self.provider_name,
            "text": "",
            "page_results": page_results,
            "layout_summary": {
                "output_dir": str(output_dir),
                "json_files": len(list(output_dir.rglob("*.json"))),
                "markdown_files": len(list(output_dir.rglob("*.md"))),
            },
        }

    def _build_command(self, pdf_path: Path, output_dir: Path) -> list[str]:
        if self.settings.mineru_executable:
            return [
                self.settings.mineru_executable,
                "-p",
                str(pdf_path),
                "-o",
                str(output_dir),
                "-m",
                "auto",
            ]
        return [
            sys.executable,
            "-m",
            "magic_pdf.tools.cli",
            "-p",
            str(pdf_path),
            "-o",
            str(output_dir),
            "-m",
            "auto",
        ]

    def get_layout_regions(self, output_dir: Path) -> dict[int, list[dict[str, Any]]]:
        regions_by_page: dict[int, list[dict[str, Any]]] = {}
        for json_path in sorted(output_dir.rglob("*.json")):
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            self._parse_json_for_regions(data, regions_by_page)
        return regions_by_page

    def _parse_json_for_regions(self, data: Any, regions_by_page: dict[int, list[dict[str, Any]]]) -> None:
        if isinstance(data, dict):
            page_no = data.get("page_no") or data.get("page_num") or data.get("page_number") or 1
            for key in ["layout_dets", "layout_res", "bbox_list", "regions"]:
                detections = data.get(key)
                if isinstance(detections, list):
                    regions_by_page.setdefault(int(page_no), [])
                    for detection in detections:
                        region = self._normalize_region(detection)
                        if region:
                            regions_by_page[int(page_no)].append(region)
            for value in data.values():
                self._parse_json_for_regions(value, regions_by_page)
        elif isinstance(data, list):
            for item in data:
                self._parse_json_for_regions(item, regions_by_page)

    def _normalize_region(self, detection: Any) -> dict[str, Any] | None:
        if not isinstance(detection, dict):
            return None
        bbox = detection.get("bbox") or detection.get("box") or detection.get("poly")
        category = detection.get("category") or detection.get("type") or detection.get("label", "unknown")
        score = detection.get("score") or detection.get("confidence", 1.0)
        if not bbox or len(bbox) < 4:
            return None
        return {
            "bbox": [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])],
            "category": str(category),
            "score": float(score),
        }


class HybridOCRBackend(BaseOCRBackend):
    """MinerU 做布局，PaddleOCR 做文字识别。"""

    provider_name = "hybrid"

    def __init__(self) -> None:
        super().__init__()
        self.mineru_backend = MinerUBackend()
        self.paddle_backend = PaddleOCRBackend()

    def ensure_available(self) -> None:
        mineru_error = None
        paddle_error = None
        try:
            self.mineru_backend.ensure_available()
        except OCRUnavailableError as error:
            mineru_error = error
        try:
            self.paddle_backend.ensure_available()
        except OCRUnavailableError as error:
            paddle_error = error
        if mineru_error and paddle_error:
            raise OCRUnavailableError(f"混合 OCR 后端不可用。MinerU: {mineru_error}; PaddleOCR: {paddle_error}")

    def extract_from_pdf(self, pdf_path: str | Path) -> dict[str, Any]:
        mineru_result: dict[str, Any] | None = None
        paddle_result: dict[str, Any] | None = None

        try:
            self.mineru_backend.ensure_available()
            mineru_result = self.mineru_backend.extract_from_pdf(pdf_path)
        except OCRUnavailableError:
            mineru_result = None

        try:
            self.paddle_backend.ensure_available()
            paddle_result = self.paddle_backend.extract_from_pdf(pdf_path)
        except OCRUnavailableError as error:
            if mineru_result is None:
                raise error
            paddle_result = None

        merged_pages: dict[int, dict[str, Any]] = {}
        if mineru_result:
            for page in mineru_result.get("page_results", []):
                merged_pages[int(page["page_number"])] = dict(page)
        if paddle_result:
            for page in paddle_result.get("page_results", []):
                page_number = int(page["page_number"])
                current = merged_pages.setdefault(
                    page_number,
                    {
                        "page_number": page_number,
                        "text": "",
                        "layout_regions": [],
                        "vision_description": None,
                    },
                )
                current["text"] = page.get("text", "")
                current["vision_description"] = page.get("vision_description")
                if not current.get("layout_regions"):
                    current["layout_regions"] = page.get("layout_regions", [])

        merged_result_pages = [merged_pages[key] for key in sorted(merged_pages.keys())]
        text_parts: list[str] = []
        for page in merged_result_pages:
            if page.get("text"):
                text_parts.append(page["text"])
            if page.get("vision_description"):
                text_parts.append(page["vision_description"])

        return {
            "provider": self.provider_name,
            "text": "\n".join(text_parts),
            "page_results": merged_result_pages,
            "layout_summary": (mineru_result or {}).get("layout_summary", {}),
        }


class AutoOCRBackend(BaseOCRBackend):
    """自动选择可用 OCR 后端。"""

    provider_name = "auto"

    def ensure_available(self) -> None:
        hybrid_backend = HybridOCRBackend()
        paddle_backend = PaddleOCRBackend()
        mineru_backend = MinerUBackend()
        errors: list[str] = []

        for backend in [hybrid_backend, paddle_backend, mineru_backend]:
            try:
                backend.ensure_available()
                self._backend = backend
                return
            except OCRUnavailableError as error:
                errors.append(f"{backend.provider_name}: {error}")
        raise OCRUnavailableError("OCR 后端都不可用，请检查依赖和配置。" + "; ".join(errors))

    def extract_from_pdf(self, pdf_path: str | Path) -> dict[str, Any]:
        if not hasattr(self, "_backend"):
            self.ensure_available()
        return self._backend.extract_from_pdf(pdf_path)
