"""文本转向量（Embedding）"""
from __future__ import annotations
import logging
from typing import List
import numpy as np

logger = logging.getLogger(__name__)


class Embedder:
    """用 bge-m3 把文本块转成向量。

    用法：
        embedder = Embedder(model_path=r'E:\AI_models\BGE-M3')
        vectors = embedder.encode(['文本1', '文本2', '文本3'])
    """

    def __init__(self, model_path: str, device: str = 'cuda', batch_size: int = 32):
        """
        Args:
            model_path: 本地模型路径。
            device: 'cuda' 用GPU，'cpu' 用CPU。
            batch_size: 批量编码大小，显存不够就调小。
        """
        from sentence_transformers import SentenceTransformer
        logger.info('加载模型: %s (%s)', model_path, device)
        self._model = SentenceTransformer(model_path, device=device)
        self._device = device
        self._batch_size = batch_size
        self._dim = self._model.get_embedding_dimension()
        logger.info('模型加载完成, 维度: %d', self._dim)

    @property
    def dim(self) -> int:
        """向量维度。"""
        return self._dim

    def encode(self, texts: List[str]) -> np.ndarray:
        """批量编码文本为向量。

        Args:
            texts: 文本列表。

        Returns:
            numpy 数组，shape = (len(texts), dim)。
        """
        if not texts:
            return np.array([])
        vectors = self._model.encode(
            texts,
            batch_size=self._batch_size,
            device=self._device,
            show_progress_bar=len(texts) > 100,
            normalize_embeddings=True,  # bge-m3 建议归一化，方便余弦相似度
        )
        logger.info('编码完成: %d 条文本 -> %s', len(texts), vectors.shape)
        return vectors
