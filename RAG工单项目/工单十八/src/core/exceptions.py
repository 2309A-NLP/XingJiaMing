from __future__ import annotations


class ApplicationError(Exception):
    """项目级基础异常。"""


class InputValidationError(ApplicationError):
    """输入不合法。"""


class OCRUnavailableError(ApplicationError):
    """OCR 能力不可用。"""


class DocumentReadError(ApplicationError):
    """文档读取失败。"""
