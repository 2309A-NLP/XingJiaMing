"""文本转向量（Embedding）

支持多种嵌入模型的动态加载和切换。
通过 EMBEDDING_MODELS 环境变量配置可用模型，格式：name:path,name:path
"""
from __future__ import annotations
import logging
import os
from typing import List, Dict, Optional
import numpy as np

logger = logging.getLogger(__name__)


def _parse_model_registry() -> Dict[str, str]:
    """从环境变量解析模型注册表

    EMBEDDING_MODELS 格式：name:path,name:path
    例如：bge-m3:E:\AI_models\BGE-M3,m3e:E:\AI_models\model-m3e-base
    """
    raw = os.getenv('EMBEDDING_MODELS', '')
    registry = {}
    if raw:
        for item in raw.split(','):
            item = item.strip()
            if ':' in item:
                name, path = item.split(':', 1)
                registry[name.strip()] = path.strip()

    # 兼容旧配置：如果没有 EMBEDDING_MODELS，用 EMBEDDING_MODEL_PATH
    if not registry:
        fallback = os.getenv('EMBEDDING_MODEL_PATH', '')
        if fallback:
            registry['default'] = fallback

    return registry


class Embedder:
    """嵌入模型管理器，支持多模型加载和切换。

    通过 model_name 参数指定使用哪个模型。
    已加载的模型会缓存，避免重复加载。
    """

    # 类级别缓存：所有 Embedder 实例共享
    _cache: Dict[str, any] = {}

    def __init__(self, model_path: str = None, device: str = 'cuda', batch_size: int = 32,
                 model_name: str = None):
        """
        Args:
            model_path: 直接指定模型路径（优先级高）。
            device: 'cuda' 用GPU，'cpu' 用CPU。
            batch_size: 批量编码大小。
            model_name: 模型名称，从注册表中查找路径。
        """
        self._registry = _parse_model_registry()
        self._device = device
        self._batch_size = batch_size
        self._current_name = None

        # 确定模型路径
        if model_name and model_name in self._registry:
            actual_path = self._registry[model_name]
            self._current_name = model_name
        elif model_path:
            actual_path = model_path
            # 反查名称
            for name, path in self._registry.items():
                if path == model_path:
                    self._current_name = name
                    break
            if not self._current_name:
                self._current_name = 'default'
        elif self._registry:
            # 使用默认模型（第一个）
            first_name = os.getenv('DEFAULT_EMBEDDING_MODEL', list(self._registry.keys())[0])
            if first_name in self._registry:
                actual_path = self._registry[first_name]
                self._current_name = first_name
            else:
                actual_path = list(self._registry.values())[0]
                self._current_name = list(self._registry.keys())[0]
        else:
            raise ValueError("没有配置嵌入模型，请在 .env 中设置 EMBEDDING_MODEL_PATH 或 EMBEDDING_MODELS")

        self._model_path = actual_path
        self._model = self._load_model(actual_path, device)
        self._dim = self._model.get_sentence_embedding_dimension()
        logger.info('Embedder 初始化完成: %s (%s), 维度: %d', self._current_name, actual_path, self._dim)

    def _load_model(self, model_path: str, device: str):
        """加载模型，使用缓存避免重复加载"""
        cache_key = f"{model_path}:{device}"
        if cache_key in Embedder._cache:
            logger.info('使用缓存模型: %s', model_path)
            return Embedder._cache[cache_key]

        from sentence_transformers import SentenceTransformer
        import torch

        logger.info('加载模型: %s (%s)', model_path, device)
        if device == 'cuda' and not torch.cuda.is_available():
            logger.warning('CUDA 不可用，回退到 CPU')
            device = 'cpu'

        model = SentenceTransformer(model_path, device=device)
        Embedder._cache[cache_key] = model
        return model

    @property
    def dim(self) -> int:
        """向量维度。"""
        return self._dim

    @property
    def current_model(self) -> str:
        """当前使用的模型名称。"""
        return self._current_name

    @property
    def available_models(self) -> Dict[str, str]:
        """所有可用模型 {name: path}。"""
        return dict(self._registry)

    def switch_model(self, model_name: str) -> bool:
        """切换到指定模型。返回是否成功。"""
        if model_name not in self._registry:
            logger.warning('模型 %s 不在注册表中，可用: %s', model_name, list(self._registry.keys()))
            return False

        if model_name == self._current_name:
            return True  # 已经是当前模型

        actual_path = self._registry[model_name]
        self._model = self._load_model(actual_path, self._device)
        self._dim = self._model.get_sentence_embedding_dimension()
        self._current_name = model_name
        logger.info('切换到模型: %s (%s), 维度: %d', model_name, actual_path, self._dim)
        return True

    def encode(self, texts: List[str]) -> np.ndarray:
        """批量编码文本为向量。"""
        if not texts:
            return np.array([])
        vectors = self._model.encode(
            texts,
            batch_size=self._batch_size,
            show_progress_bar=len(texts) > 100,
            normalize_embeddings=True,
        )
        logger.info('编码完成: %d 条文本 -> %s (模型: %s)', len(texts), vectors.shape, self._current_name)
        return vectors
