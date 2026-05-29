# -*- coding: utf-8 -*-
"""
PDF文件加载模块（已增强）
支持纯文本PDF和图片PDF（通过OCR）
保持向后兼容性，同时提供增强功能
"""

from .load_file import load_pdf as enhanced_load_pdf, load_file

def load_pdf(pdf_path: str) -> str:
    """
    读取PDF文件，返回全部文本
    支持纯文本PDF和图片PDF（自动检测并使用OCR）
    :param pdf_path: PDF文件路径
    :return: 文本字符串
    :raises FileNotFoundError: 若PDF文件不存在
    :raises ValueError: 若文件不是PDF格式
    :raises RuntimeError: 若解析失败
    """
    return enhanced_load_pdf(pdf_path, use_ocr=True)