"""多种重排算法模块

支持的重排算法：
1. bge - BGE-Reranker（基于深度学习）
2. llm - LLM-Reranker（基于大语言模型）
3. tfidf - TF-IDF-Reranker（基于 TF-IDF 相似度）
4. adaptive - 自适应重排器（结合多种算法）
"""
from __future__ import annotations
import logging
import os
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseReranker(ABC):
    """重排器基类"""

    @abstractmethod
    def rerank(self, query: str, candidates: List[dict], top_k: int = 5) -> List[dict]:
        """对候选结果重新打分排序"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """重排器名称"""
        pass


class BGEReranker(BaseReranker):
    """BGE-Reranker：基于深度学习的重排器"""

    def __init__(self, model_path: str, device: str = 'cpu'):
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        import torch
        logger.info('加载 BGE-Reranker 模型: %s', model_path)
        self._tokenizer = AutoTokenizer.from_pretrained(model_path)
        self._model = AutoModelForSequenceClassification.from_pretrained(model_path)
        self._model = self._model.to('cpu').eval()
        if device == 'cuda' and torch.cuda.is_available():
            self._model = self._model.to(device).eval()
            logger.info('BGE-Reranker 已迁移到 CUDA')
        self._device = device
        logger.info('BGE-Reranker 加载完成')

    @property
    def name(self) -> str:
        return "bge"

    def rerank(self, query: str, candidates: List[dict], top_k: int = 5) -> List[dict]:
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


class LLMReranker(BaseReranker):
    """LLM-Reranker：基于大语言模型的重排器

    使用 LLM 对候选结果进行相关性评分。
    适合对准确率要求高的场景，但速度较慢。
    """

    def __init__(self):
        self._api_key = os.getenv('MIMO_API_KEY', '')
        self._base_url = os.getenv('MIMO_BASE_URL', 'https://api.deepseek.com/v1')
        self._model = os.getenv('MIMO_MODEL', 'deepseek-chat')
        logger.info('LLM-Reranker 初始化完成')

    @property
    def name(self) -> str:
        return "llm"

    def rerank(self, query: str, candidates: List[dict], top_k: int = 5) -> List[dict]:
        if not candidates:
            return []

        import requests

        # 构建 prompt，让 LLM 对候选结果评分
        candidates_text = ""
        for i, c in enumerate(candidates[:10]):  # 最多评 10 个
            content = c['content'][:200]  # 截断避免 token 过多
            candidates_text += f"\n[{i}] {content}"

        prompt = f"""请对以下检索结果与查询的相关性进行评分（0-10分）。
查询：{query}
检索结果：{candidates_text}

请返回 JSON 格式，包含每个结果的索引和分数，例如：
{{"scores": [{{"index": 0, "score": 8}}, {{"index": 1, "score": 6}}]}}
只返回 JSON，不要其他内容。"""

        try:
            response = requests.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 500
                },
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']

                # 解析 JSON 响应
                import json
                # 提取 JSON 部分
                json_start = content.find('{')
                json_end = content.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    scores_data = json.loads(content[json_start:json_end])
                    scores = {item['index']: item['score'] for item in scores_data['scores']}

                    # 按分数排序
                    sorted_candidates = []
                    for i, c in enumerate(candidates[:10]):
                        if i in scores:
                            c['rerank_score'] = scores[i]
                            sorted_candidates.append(c)

                    sorted_candidates.sort(key=lambda x: x.get('rerank_score', 0), reverse=True)
                    return sorted_candidates[:top_k]

        except Exception as e:
            logger.warning('LLM-Reranker 调用失败: %s', e)

        # 失败时返回原始顺序
        return candidates[:top_k]


class TFIDFReranker(BaseReranker):
    """TF-IDF-Reranker：基于 TF-IDF 相似度的重排器

    使用 TF-IDF 向量化计算查询与文档的相似度。
    速度快，适合对响应时间要求高的场景。
    """

    def __init__(self):
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        self._vectorizer = TfidfVectorizer(
            analyzer='char_wb',
            ngram_range=(2, 4),
            max_features=10000
        )
        self._cosine_similarity = cosine_similarity
        logger.info('TF-IDF-Reranker 初始化完成')

    @property
    def name(self) -> str:
        return "tfidf"

    def rerank(self, query: str, candidates: List[dict], top_k: int = 5) -> List[dict]:
        if not candidates:
            return []

        # 构建文档列表
        documents = [c['content'] for c in candidates]
        all_texts = [query] + documents

        # 计算 TF-IDF 相似度
        try:
            tfidf_matrix = self._vectorizer.fit_transform(all_texts)
            similarities = self._cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]

            # 按相似度排序
            sorted_pairs = sorted(zip(similarities, candidates), key=lambda x: x[0], reverse=True)

            results = []
            for score, c in sorted_pairs[:top_k]:
                c['rerank_score'] = float(score)
                results.append(c)

            return results

        except Exception as e:
            logger.warning('TF-IDF-Reranker 计算失败: %s', e)
            return candidates[:top_k]


class AdaptiveReranker(BaseReranker):
    """自适应重排器：结合多种算法

    根据查询特征自动选择最合适的重排策略：
    - 短查询（<10字）：使用 TF-IDF（速度快）
    - 长查询（>=10字）：使用 BGE（准确率高）
    - 备选：使用 LLM（最准确但最慢）
    """

    def __init__(self, bge_reranker: Optional[BGEReranker] = None,
                 llm_reranker: Optional[LLMReranker] = None,
                 tfidf_reranker: Optional[TFIDFReranker] = None):
        self._bge = bge_reranker
        self._llm = llm_reranker
        self._tfidf = tfidf_reranker or TFIDFReranker()
        logger.info('Adaptive-Reranker 初始化完成')

    @property
    def name(self) -> str:
        return "adaptive"

    def rerank(self, query: str, candidates: List[dict], top_k: int = 5) -> List[dict]:
        if not candidates:
            return []

        query_len = len(query)

        # 短查询用 TF-IDF
        if query_len < 10 and self._tfidf:
            logger.info('自适应选择: TF-IDF（短查询）')
            return self._tfidf.rerank(query, candidates, top_k)

        # 长查询用 BGE
        if query_len >= 10 and self._bge:
            logger.info('自适应选择: BGE（长查询）')
            return self._bge.rerank(query, candidates, top_k)

        # 备选：用 LLM
        if self._llm:
            logger.info('自适应选择: LLM（备选）')
            return self._llm.rerank(query, candidates, top_k)

        # 最后兜底：TF-IDF
        logger.info('自适应选择: TF-IDF（兜底）')
        return self._tfidf.rerank(query, candidates, top_k)


def create_reranker(reranker_type: str = "bge", **kwargs) -> BaseReranker:
    """工厂函数：创建重排器实例

    Args:
        reranker_type: 重排器类型，可选值：bge, llm, tfidf, adaptive
        **kwargs: 传递给重排器的参数

    Returns:
        BaseReranker 实例
    """
    rerankers = {
        "bge": BGEReranker,
        "llm": LLMReranker,
        "tfidf": TFIDFReranker,
        "adaptive": AdaptiveReranker,
    }

    if reranker_type not in rerankers:
        logger.warning('未知的重排器类型: %s，使用默认 BGE', reranker_type)
        reranker_type = "bge"

    reranker_class = rerankers[reranker_type]

    # 根据类型传递不同的参数
    if reranker_type == "bge":
        model_path = kwargs.get('model_path', os.getenv('RERANK_MODEL_PATH', ''))
        device = kwargs.get('device', 'cuda')
        return reranker_class(model_path=model_path, device=device)
    elif reranker_type == "adaptive":
        # 自适应重排器需要其他重排器实例
        bge = kwargs.get('bge_reranker')
        llm = kwargs.get('llm_reranker')
        tfidf = kwargs.get('tfidf_reranker')
        return reranker_class(bge_reranker=bge, llm_reranker=llm, tfidf_reranker=tfidf)
    else:
        return reranker_class()