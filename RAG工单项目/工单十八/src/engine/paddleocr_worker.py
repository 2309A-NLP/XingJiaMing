from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    payload = json.loads(sys.argv[1])
    result = run_worker(
        pdf_path=payload["pdf_path"],
        lang=payload.get("lang", "ch"),
        render_scale=float(payload.get("render_scale", 2.0)),
    )
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


def run_worker(pdf_path: str, lang: str, render_scale: float) -> dict:
    import fitz
    import numpy as np
    from paddleocr import PaddleOCR

    reader = fitz.open(str(Path(pdf_path)))
    ocr = PaddleOCR(lang=lang)
    page_results: list[dict] = []
    full_text_parts: list[str] = []

    for page_index in range(reader.page_count):
        page = reader.load_page(page_index)
        pix = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale), alpha=False)
        image_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
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
        full_text_parts.append(page_text)
        page_results.append(
            {
                "page_number": page_index + 1,
                "text": page_text,
                "layout_regions": [],
                "vision_description": None,
            }
        )

    reader.close()
    return {
        "provider": "paddleocr",
        "text": "\n".join(part for part in full_text_parts if part),
        "page_results": page_results,
        "layout_summary": {"mode": "subprocess"},
    }


if __name__ == "__main__":
    main()
