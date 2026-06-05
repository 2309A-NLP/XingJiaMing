"""TextFallbackEngine - 文本提取兜底引擎

当 MinerU 和 PaddleOCR 都不可用或失败时，
使用 pypdfium2 直接提取 PDF 中的文本。
"""

from __future__ import annotations
import logging
from PIL import Image
from scripts.engine.base import BaseEngine

logger = logging.getLogger(__name__)


class TextFallbackEngine(BaseEngine):
    """基于 pypdfium2 的文本提取引擎。直接从 PDF 提取文本，无需 ML 模型。"""

    @property
    def name(self) -> str:
        return "text_fallback"

    def is_available(self) -> bool:
        try:
            import pypdfium2
            return True
        except ImportError:
            return False

    def initialize(self) -> None:
        pass

    def process_page(self, image: Image.Image, page_no: int) -> str:
        """实际文本提取在 BatchProcessor 中通过 pypdfium2 直接完成。"""
        return ""