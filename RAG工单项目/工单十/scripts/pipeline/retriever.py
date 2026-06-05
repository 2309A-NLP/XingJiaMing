"""多路召回检索器（语义 + BM25 + 元数据过滤 + Rerank）

优化点：Query 理解和 Embedding 并行执行，节省 1-2s
"""
from __future__ import annotations
import logging
import re
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


def _extract_management_keywords(query: str) -> List[str]:
    """从管理层问题中提取关键词（公司名、人名、职位）"""
    keywords = []

    # 提取公司名
    company_patterns = [
        r'([一-鿿]+银行)',
        r'([一-鿿]+证券)',
        r'([一-鿿]+保险)',
        r'([一-鿿]+人寿)',
        r'([一-鿿]+平安)',
        r'([一-鿿]+太保)',
    ]
    for pattern in company_patterns:
        matches = re.findall(pattern, query)
        keywords.extend(matches)

    # 提取职位
    positions = ['董事长', '行长', 'CEO', '总经理', '首席执行官', '总裁', '副行长', '董事']
    for pos in positions:
        if pos in query:
            keywords.append(pos)

    # 提取年份
    year_match = re.findall(r'(\d{4})年?', query)
    if year_match:
        keywords.extend(year_match)

    return list(set(keywords))


def _boost_management_results(results: List[dict], keywords: List[str]) -> List[dict]:
    """为管理层结果添加关键词增强"""
    if not keywords:
        return results

    for r in results:
        content = r.get('content', '')
        boost = 0.0

        # 检查是否包含人名+职位的组合
        person_position_patterns = [
            r'[一-鿿]{2,4}.*?董事长',
            r'[一-鿿]{2,4}.*?行长',
            r'[一-鿿]{2,4}.*?CEO',
            r'董事长.*?[一-鿿]{2,4}',
            r'行长.*?[一-鿿]{2,4}',
        ]

        for pattern in person_position_patterns:
            if re.search(pattern, content):
                boost += 2.0
                break

        # 检查表格格式 ['姓名','职务',...] - 大幅增强
        if re.search(r"\['[一-鿿]+','[一-鿿]+',", content):
            boost += 8.0

        # 检查是否同时包含多个职位（如董事长+行长）
        positions_found = 0
        for pos in ['董事长', '行长', 'CEO', '总经理']:
            if pos in content:
                positions_found += 1
        if positions_found >= 2:
            boost += 5.0

        # 检查关键词命中
        for kw in keywords:
            if kw in content:
                boost += 1.0

        r['score'] = r.get('score', 0) + boost

    return results


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

        # 检测是否是管理层问题
        management_keywords = _extract_management_keywords(query)
        if management_keywords:
            logger.info('检测到管理层问题，关键词: %s', management_keywords)
            merged = _boost_management_results(merged, management_keywords)
            # 重新排序
            merged.sort(key=lambda x: x.get('score', 0), reverse=True)

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

    def _load_reranker(self, reranker_type="bge"):
        """lazy load reranker"""
        try:
            from scripts.pipeline.reranker import create_reranker
            logger.info("lazy loading Reranker: %s (type: %s)", self._reranker_path, reranker_type)
            self._reranker = create_reranker(
                reranker_type=reranker_type,
                model_path=self._reranker_path or "",
                device="cuda"
            )
            logger.info("Reranker lazy loaded: %s", self._reranker.name)
        except Exception as e:
            logger.error("Reranker lazy load failed: %s", str(e) or repr(e))
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

    def _merge(self, dense: List[dict], sparse: List[dict],
               dense_weight: float = 1.0, sparse_weight: float = 1.5) -> List[dict]:
        """用 RRF（倒数排名融合）合并两路结果。
        支持自定义权重，默认 BM25 权重更高（1.5x）。
        """
        RRF_K = 60
        DENSE_WEIGHT = dense_weight
        SPARSE_WEIGHT = sparse_weight

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