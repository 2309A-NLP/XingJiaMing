"""Rerank 精排器（BGE-Reranker）"""
from __future__ import annotations
import logging
from typing import List

logger = logging.getLogger(__name__)


class Reranker:
    """用 BGE-Reranker 对检索结果重新打分排序。"""

    def __init__(self, model_path: str, device: str = 'cpu'):
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        import torch
        logger.info('加载 Reranker 模型: %s', model_path)
        self._tokenizer = AutoTokenizer.from_pretrained(model_path)
        self._model = AutoModelForSequenceClassification.from_pretrained(model_path)
        # 先 CPU 加载再迁移，避免 meta tensor 问题
        self._model = self._model.to('cpu').eval()
        if device == 'cuda' and torch.cuda.is_available():
            self._model = self._model.to(device).eval()
            logger.info('Reranker 已迁移到 CUDA')
        self._device = device
        logger.info('Reranker 加载完成')

    def rerank(self, query: str, candidates: List[dict], top_k: int = 5) -> List[dict]:
        """对候选结果重新打分排序。"""
        if not candidates:
            return []

        import torch

        scores = []
        for c in candidates:
            inputs = self._tokenizer(
                query, c['content'],
                return_tensors='pt',
                truncation=True,
                max_length=512,
            ).to(self._device)
            with torch.no_grad():
                score = self._model(**inputs).logits.item()
            scores.append(score)

        sorted_pairs = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)

        results = []
        for score, c in sorted_pairs[:top_k]:
            c['rerank_score'] = score
            results.append(c)

        return results