"""Rerank 精排器（BGE-Reranker）"""
from __future__ import annotations
import logging
from typing import List

logger = logging.getLogger(__name__)


class Reranker:
    """用 BGE-Reranker 对检索结果重新打分排序。

    用法：
        reranker = Reranker(model_path=r'E:\AI_models\bge-reranker-base')
        results = reranker.rerank(query, candidates, top_k=5)
    """

    def __init__(self, model_path: str, device: str = 'cpu'):
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        import torch
        logger.info('加载 Reranker 模型: %s', model_path)
        self._tokenizer = AutoTokenizer.from_pretrained(model_path)
        self._model = AutoModelForSequenceClassification.from_pretrained(model_path)
        self._model.to(device).eval()
        self._device = device
        logger.info('Reranker 加载完成')

    def rerank(self, query: str, candidates: List[dict], top_k: int = 5) -> List[dict]:
        """对候选结果重新打分排序。

        Args:
            query: 用户问题。
            candidates: 候选结果列表（每个是 dict，需有 content 字段）。
            top_k: 返回数量。

        Returns:
            重新排序后的 top_k 结果。
        """
        if not candidates:
            return []

        import torch

        # 计算每个候选的 rerank 得分
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

        # 按 rerank 得分排序
        sorted_pairs = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)

        results = []
        for score, c in sorted_pairs[:top_k]:
            c['rerank_score'] = score
            results.append(c)

        return results
