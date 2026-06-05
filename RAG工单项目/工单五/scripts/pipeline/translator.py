"""翻译模块 - 支持中英文双向翻译"""
from __future__ import annotations
import logging
import os
from openai import OpenAI

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> OpenAI:
    """懒加载 OpenAI 客户端"""
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.getenv('MIMO_API_KEY'),
            base_url=os.getenv('MIMO_BASE_URL'),
            timeout=8.0,
        )
    return _client


def translate_text(text: str, source_lang: str = "zh", target_lang: str = "en") -> str:
    """通用翻译函数。
    
    Args:
        text: 要翻译的文本
        source_lang: 源语言 zh/en
        target_lang: 目标语言 zh/en
        
    Returns:
        翻译后的文本
    """
    client = _get_client()
    model = os.getenv('MIMO_MODEL', 'deepseek-chat')
    
    # 简短的 prompt，提高速度
    if source_lang == "zh" and target_lang == "en":
        prompt = "Translate to English. Only output translation."
    elif source_lang == "en" and target_lang == "zh":
        prompt = "翻译成中文。只输出翻译结果。"
    else:
        prompt = f"Translate to {target_lang}. Only output translation."
    
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': prompt},
                {'role': 'user', 'content': text},
            ],
            temperature=0,
            max_tokens=100,
        )
        translated = resp.choices[0].message.content.strip()
        logger.info('翻译完成: %s -> %s', text[:30], translated[:30])
        return translated
    except Exception as e:
        logger.error('翻译失败: %s', str(e))
        return text


def translate_to_chinese(text: str) -> str:
    """将英文翻译成中文，用于 BM25 检索。"""
    return translate_text(text, "en", "zh")