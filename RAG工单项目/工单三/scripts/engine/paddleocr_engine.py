"""PaddleOCREngine - PaddleOCR 文字识别引擎（适配 PaddleOCR 3.5.x API）

使用说明:
  - 自动检查 PaddleOCR 是否可用（import 检查）
  - 延迟初始化（首次 process_page 时加载模型）
  - 将 OCR 识别结果拼接为纯文本返回
  - 失败时返回空字符串，不影响主流程
"""

from __future__ import annotations
import os
import sys

# 在任何其他 import 之前设置 torch 路径到 PATH，解决 shm.dll 加载问题
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.join(_current_dir, '..', '..')
_torch_lib_path = os.path.abspath(os.path.join(_project_root, '.venv', 'lib', 'site-packages', 'torch', 'lib'))
if os.path.exists(_torch_lib_path):
    os.environ['PATH'] = _torch_lib_path + ';' + os.environ.get('PATH', '')

import logging
import numpy as np
from PIL import Image
from scripts.engine.base import BaseEngine

logger = logging.getLogger(__name__)


class PaddleOCREngine(BaseEngine):
    """基于 PaddleOCR 的文字识别引擎。

    封装 PaddleOCR 3.5.x 的 ocr API，将页面图片中识别出的文字逐行拼接返回。
    支持中文/英文等多语言识别。
    """

    def __init__(self, lang: str = "ch"):
        """初始化引擎。

        Args:
            lang: OCR 语言，默认 "ch"（中文）。可选 "en", "fr", "japan" 等。
        """
        os.environ['GLOG_minloglevel'] = '2'
        self._lang = lang
        self._ocr = None
        self._initialized = False
        self._gpu_available = self._check_gpu()

    @property
    def name(self) -> str:
        """引擎名称标识，用于日志和状态记录。"""
        return "paddleocr"

    def is_available(self) -> bool:
        """检查 PaddleOCR 是否可用（依赖是否已安装）。

        Returns:
            如果 paddleocr 模块可导入则返回 True。
        """
        try:
            import paddleocr
            return True
        except ImportError:
            return False

    def _check_gpu(self) -> bool:
        try:
            import paddle
            return paddle.is_compiled_with_cuda()
        except Exception:
            return False

    def initialize(self) -> None:
        """初始化 PaddleOCR 实例（延迟加载，首次调用 process_page 时执行）。"""
        if self._initialized:
            return
        from paddleocr import PaddleOCR
        self._ocr = PaddleOCR(lang=self._lang)
        self._initialized = True
        logger.info("PaddleOCR 初始化完成 (lang=%s)", self._lang)

    def process_page(self, image: Image.Image, page_no: int) -> str:
        """处理单页图片，返回 OCR 识别出的纯文本。

        Args:
            image: PIL Image 对象。
            page_no: 页码（从 1 开始），仅用于日志记录。

        Returns:
            识别结果的纯文本字符串，失败返回空字符串。
        """
        self.initialize()
        try:
            img_array = np.array(image.convert("RGB"))
            result = self._ocr.ocr(img_array)

            lines = []
            if result and isinstance(result, list):
                for page_result in result:
                    if page_result and isinstance(page_result, list):
                        for line in page_result:
                            if isinstance(line, list) and len(line) >= 2:
                                text_info = line[1]
                                if isinstance(text_info, (list, tuple)) and len(text_info) >= 1:
                                    text = str(text_info[0]).strip()
                                    if text:
                                        lines.append(text)

            return "\n".join(lines)

        except PermissionError as e:
            logger.warning("PaddleOCR 权限错误 (第%d页): %s", page_no, e)
            return ""
        except Exception as e:
            logger.debug("PaddleOCR 失败(将走兜底) (第%d页): %s", page_no, e)
            return ""

    def cleanup(self) -> None:
        """释放 OCR 引擎占用的资源。"""
        self._ocr = None
        import gc
        gc.collect()