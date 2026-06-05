"""BM25 关键词检索（jieba 分词版）

用 jieba 做中文分词，比字符级分词效果好很多：
- "人工智能" 不会被拆成 "人" "工" "智" "能" 四个字
- 专业术语（如 "招股说明书"）能作为整体匹配
"""
from __future__ import annotations
import logging
import re
from typing import List
import jieba
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

# 停用词：常见的无意义词，过滤掉能减少噪音
_STOPWORDS = frozenset([
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那",
    "吗", "吧", "啊", "呢", "嗯", "哦", "哈", "呀", "嘛", "啦",
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "and", "but", "or",
    "not", "no", "so", "if", "then", "than", "that", "this", "these",
    "those", "it", "its", "they", "them", "their", "we", "our", "you",
])


def _tokenize(text: str) -> List[str]:
    """jieba 分词 + 过滤停用词和单字符"""
    # 清理特殊字符，保留中文和英文数字
    text = re.sub(r'[^\u4e00-\u9fff\w\s]', ' ', text)
    words = jieba.lcut(text)
    # 过滤：去掉停用词、空白、长度<2的词（保留有意义的单字如"股"）
    return [w.strip().lower() for w in words if w.strip() and w.strip().lower() not in _STOPWORDS and len(w.strip()) >= 2]


class BM25Retriever:
    """BM25 关键词检索器。"""

    def __init__(self, chunks: list):
        self._chunks = chunks
        self._texts = [c.content for c in chunks]
        if chunks:
            tokenized = [_tokenize(t) for t in self._texts]
            self._bm25 = BM25Okapi(tokenized)
            logger.info('BM25 索引建立完成: %d 个文档', len(chunks))
        else:
            self._bm25 = None
            logger.info('BM25 初始化为空')

    def search(self, query: str, top_k: int = 20) -> List[dict]:
        if not self._bm25:
            return []
        tokens = _tokenize(query)
        scores = self._bm25.get_scores(tokens)
        top_indices = scores.argsort()[-top_k:][::-1]
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append({
                    'chunk_id': self._chunks[idx].chunk_id,
                    'parent_id': self._chunks[idx].parent_id,
                    'content': self._texts[idx],
                    'section_title': self._chunks[idx].metadata.get('section_title', ''),
                    'page_numbers': self._chunks[idx].metadata.get('page_numbers', []),
                    'score': float(scores[idx]),
                })
        return results
