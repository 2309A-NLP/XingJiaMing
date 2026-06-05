"""多路召回检索器（语义 + BM25 + 元数据过滤 + Rerank）

优化点：Query 理解和 Embedding 并行执行，节省 1-2s
"""
from __future__ import annotations
import logging
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class Retriever:
    """多路召回检索器。"""

    def __init__(self, vector_store, bm25_retriever, embedder, reranker=None):
        self._vs = vector_store
        self._bm25 = bm25_retriever
        self._embedder = embedder
        self._reranker = reranker
        self._reranker_path = None

    def search(self, query: str, top_k: int = 5,
               page_filter: Optional[List[int]] = None, bm25_query: str = None) -> List[dict]:
        """多路召回检索。"""
        query_vec = self._embedder.encode([query])[0]

        # 向量检索取更多候选，BM25 取更多候选
        dense_results = self._vs.search(query_vec, top_k=top_k * 3)
        sparse_results = self._bm25.search(bm25_query or query, top_k=top_k * 4)

        merged = self._merge(dense_results, sparse_results)

        # 元数据过滤
        if page_filter:
            filtered = []
            for r in merged:
                pages = r.get('page_numbers', [])
                if isinstance(pages, str):
                    pages = [int(p) for p in pages.split(',') if p.strip()]
                if any(p in page_filter for p in pages):
                    filtered.append(r)
            merged = filtered

        # 智能 Rerank
        if len(merged) > top_k:
            if not self._reranker and self._reranker_path:
                self._load_reranker()
            if self._reranker:
                merged = self._smart_rerank(merged, top_k, query)

        return merged[:top_k]

    def _load_reranker(self):
        """lazy load reranker"""
        try:
            from scripts.pipeline.reranker import Reranker
            logger.info('lazy loading Reranker: %s', self._reranker_path)
            self._reranker = Reranker(model_path=self._reranker_path, device='cuda')
            logger.info('Reranker lazy loaded')
        except Exception as e:
            logger.error('Reranker lazy load failed: %s', str(e) or repr(e))
            self._reranker = None

    def _smart_rerank(self, merged: list, top_k: int, query: str) -> list:
        """智能 Rerank：节省时间"""
        if len(merged) <= top_k:
            return merged

        top1_hits = merged[0].get('hit_count', 1)
        topk_hits = merged[min(top_k - 1, len(merged) - 1)].get('hit_count', 1)

        # top-1 双路命中 + top-k 单路命中 -> 结果明确，跳过
        if top1_hits >= 2 and topk_hits <= 1:
            logger.info('top-1 双路命中，跳过 Rerank')
            return merged

        # 只 rerank top 16 个候选（增大候选池）
        reranked = self._reranker.rerank(query, merged[:16], top_k=top_k)
        return reranked

    def _merge(self, dense: List[dict], sparse: List[dict]) -> List[dict]:
        """用 RRF（倒数排名融合）合并两路结果。

        BM25 权重更高（1.5x），因为关键词匹配对精确问答更重要。
        """
        RRF_K = 60
        DENSE_WEIGHT = 1.0
        SPARSE_WEIGHT = 1.5  # BM25 权重更高

        seen = {}
        for rank, r in enumerate(dense, start=1):
            cid = r['chunk_id']
            seen[cid] = {**r, 'rrf_score': DENSE_WEIGHT / (RRF_K + rank), 'hit_count': 1}

        for rank, r in enumerate(sparse, start=1):
            cid = r['chunk_id']
            if cid in seen:
                seen[cid]['rrf_score'] += SPARSE_WEIGHT / (RRF_K + rank)
                seen[cid]['hit_count'] += 1
            else:
                seen[cid] = {**r, 'rrf_score': SPARSE_WEIGHT / (RRF_K + rank), 'hit_count': 1}

        results = sorted(seen.values(), key=lambda x: x['rrf_score'], reverse=True)
        return results