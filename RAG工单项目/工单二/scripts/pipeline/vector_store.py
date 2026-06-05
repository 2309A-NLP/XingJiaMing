"""向量存储（Milvus）"""
from __future__ import annotations
import logging
from typing import List
import numpy as np
from pymilvus import MilvusClient, DataType

logger = logging.getLogger(__name__)


class VectorStore:
    """Milvus 向量存储，负责存入和检索向量。"""

    def __init__(self, host: str = 'localhost', port: str = '19530',
                 collection: str = 'rag_child_chunks'):
        self._client = MilvusClient(uri='http://%s:%s' % (host, port))
        self._collection = collection

    def create(self, dim: int) -> None:
        """创建集合，如果已存在就先删再建。"""
        if self._client.has_collection(self._collection):
            self._client.drop_collection(self._collection)

        schema = self._client.create_schema(auto_id=False)
        schema.add_field('chunk_id', DataType.VARCHAR, is_primary=True, max_length=20)
        schema.add_field('parent_id', DataType.VARCHAR, max_length=20)
        schema.add_field('content', DataType.VARCHAR, max_length=8000)
        schema.add_field('section_title', DataType.VARCHAR, max_length=500)
        schema.add_field('page_numbers', DataType.VARCHAR, max_length=200)
        schema.add_field('vector', DataType.FLOAT_VECTOR, dim=dim)

        index_params = self._client.prepare_index_params()
        index_params.add_index('vector', index_type='IVF_FLAT', metric_type='COSINE', params={'nlist': 128})

        self._client.create_collection(self._collection, schema=schema, index_params=index_params)
        logger.info('集合创建完成: %s (dim=%d)', self._collection, dim)

    def insert(self, chunks: list, vectors: np.ndarray) -> None:
        """批量插入子块和对应的向量。"""
        rows = []
        for chunk, vec in zip(chunks, vectors):
            pages = chunk.metadata.get('page_numbers', [])
            rows.append({
                'chunk_id': chunk.chunk_id,
                'parent_id': chunk.parent_id,
                'content': chunk.content[:7999],
                'section_title': chunk.metadata.get('section_title', ''),
                'page_numbers': ','.join(str(p) for p in pages),
                'vector': vec.tolist(),
            })
        self._client.insert(self._collection, rows)
        self._client.flush(self._collection)
        logger.info('插入 %d 条到 Milvus', len(rows))

    def search(self, query_vector: np.ndarray, top_k: int = 5) -> List[dict]:
        """向量检索，返回最相似的 top_k 个子块。"""
        try:
            results = self._client.search(
                self._collection,
                data=[query_vector.tolist()],
                limit=top_k,
                output_fields=['chunk_id', 'parent_id', 'content', 'section_title', 'page_numbers'],
            )
            hits = []
            for hit in results[0]:
                hits.append({
                    'chunk_id': hit['entity']['chunk_id'],
                    'parent_id': hit['entity']['parent_id'],
                    'content': hit['entity']['content'],
                    'section_title': hit['entity']['section_title'],
                    'page_numbers': hit['entity']['page_numbers'],
                    'score': hit['distance'],
                })
            return hits
        except Exception as e:
            logger.error('Milvus 检索失败: %s', e)
            return []


    def count(self) -> int:
        """返回集合中的向量数量。"""
        self._client.flush(self._collection)
        return self._client.get_collection_stats(self._collection)['row_count']

    def drop(self) -> None:
        """删除集合。"""
        if self._client.has_collection(self._collection):
            self._client.drop_collection(self._collection)

