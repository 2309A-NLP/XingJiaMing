"""向量存储（Milvus）

支持多文档共存，通过 source_file 区分文档来源。
新文档入库时会检查是否已有相同内容（去重）。
"""
from __future__ import annotations
import hashlib
import logging
from typing import List, Optional
import numpy as np
from pymilvus import MilvusClient, DataType

logger = logging.getLogger(__name__)


class VectorStore:
    """Milvus 向量存储，负责存入和检索向量。"""

    def __init__(self, host: str = 'localhost', port: str = '19530',
                 collection: str = 'rag_child_chunks'):
        self._client = MilvusClient(uri='http://%s:%s' % (host, port))
        self._collection = collection

    def _collection_exists(self) -> bool:
        """兼容不同 pymilvus 版本的集合存在性检查。"""
        has_collection = getattr(self._client, 'has_collection', None)
        if callable(has_collection):
            return bool(has_collection(self._collection))
        list_collections = getattr(self._client, 'list_collections', None)
        if callable(list_collections):
            return self._collection in set(list_collections())
        return False

    @staticmethod
    def _extract_row_count(stats) -> int:
        """兼容不同 Milvus stats 返回结构。"""
        if isinstance(stats, dict):
            value = stats.get('row_count', 0)
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0

        if isinstance(stats, list):
            total = 0
            for item in stats:
                if isinstance(item, dict) and item.get('key') == 'row_count':
                    try:
                        return int(item.get('value', 0))
                    except (TypeError, ValueError):
                        return 0
                key = getattr(item, 'key', None)
                if key == 'row_count':
                    try:
                        return int(getattr(item, 'value', 0))
                    except (TypeError, ValueError):
                        return 0
                if isinstance(item, int):
                    total += item
            if total:
                return total
        return 0

    def create(self, dim: int, force_rebuild: bool = False) -> None:
        """创建集合。如果已存在且 force_rebuild=False，跳过创建。"""
        if self._collection_exists():
            if not force_rebuild:
                logger.info("集合 %s 已存在，跳过创建", self._collection)
                return
            logger.info("强制重建集合 %s", self._collection)
            self._client.drop_collection(self._collection)

        schema = self._client.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field('chunk_id', DataType.VARCHAR, is_primary=True, max_length=32)
        schema.add_field('parent_id', DataType.VARCHAR, max_length=20)
        schema.add_field('content', DataType.VARCHAR, max_length=8000)
        schema.add_field('section_title', DataType.VARCHAR, max_length=500)
        schema.add_field('page_numbers', DataType.VARCHAR, max_length=200)
        schema.add_field('source_file', DataType.VARCHAR, max_length=200)
        schema.add_field('content_hash', DataType.VARCHAR, max_length=32)
        schema.add_field('vector', DataType.FLOAT_VECTOR, dim=dim)
        schema.verify()

        index_params = self._client.prepare_index_params(
            'vector',
            index_type='IVF_FLAT',
            metric_type='COSINE',
            params={'nlist': 128},
        )

        create_collection = getattr(self._client, 'create_collection', None)
        conn = getattr(self._client, '_get_connection', lambda: None)()
        if conn and hasattr(conn, 'create_collection'):
            conn.create_collection(self._collection, schema, consistency_level='Strong')
            create_index = getattr(self._client, '_create_index', None)
            if callable(create_index):
                create_index(self._collection, 'vector', index_params)
            load_collection = getattr(self._client, '_load', None)
            if callable(load_collection):
                load_collection(self._collection)
        elif callable(create_collection):
            create_collection(
                self._collection,
                dimension=dim,
                primary_field_name='chunk_id',
                id_type='string',
                vector_field_name='vector',
                metric_type='COSINE',
                auto_id=False,
                max_length=32,
            )
        logger.info('集合创建完成: %s (dim=%d)', self._collection, dim)

    def _compute_hash(self, content: str) -> str:
        """计算内容哈希，用于去重判断"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()[:16]

    def get_existing_hashes(self, source_file: str = None) -> set:
        """获取已存在的内容哈希集合，用于去重判断"""
        try:
            if not self._collection_exists():
                return set()
            if source_file:
                results = self._client.query(
                    self._collection,
                    filter=f'source_file == "{source_file}"',
                    output_fields=['content_hash'],
                    limit=10000,
                )
            else:
                results = self._client.query(
                    self._collection,
                    filter='content_hash != ""',
                    output_fields=['content_hash'],
                    limit=10000,
                )
            return {r['content_hash'] for r in results}
        except Exception as e:
            logger.warning('获取哈希集合失败: %s', e)
            return set()

    def query_by_source(self, source_file: str) -> list:
        """查询指定文档来源的所有记录，用于判断文档是否已入库"""
        try:
            if not self._collection_exists():
                return []
            results = self._client.query(
                self._collection,
                filter=f'source_file == "{source_file}"',
                output_fields=['chunk_id'],
                limit=10000,
            )
            return results
        except Exception as e:
            logger.warning('查询文档来源失败: %s', e)
            return []

    def insert(self, chunks: list, vectors: np.ndarray, source_file: str = '') -> tuple:
        """批量插入子块和对应的向量。自动去重。"""
        existing_hashes = self.get_existing_hashes()

        rows = []
        skipped = 0
        for chunk, vec in zip(chunks, vectors):
            content = chunk.content[:7999]
            content_hash = self._compute_hash(content)
            if content_hash in existing_hashes:
                skipped += 1
                continue
            pages = chunk.metadata.get('page_numbers', [])
            rows.append({
                'chunk_id': chunk.chunk_id,
                'parent_id': chunk.parent_id,
                'content': content,
                'section_title': chunk.metadata.get('section_title', ''),
                'page_numbers': ','.join(str(p) for p in pages),
                'source_file': source_file,
                'content_hash': content_hash,
                'vector': vec.tolist(),
            })
            existing_hashes.add(content_hash)

        if rows:
            self._client.insert(self._collection, rows)
            self._client.flush(self._collection)
            logger.info('插入 %d 条到 Milvus (跳过 %d 条重复)', len(rows), skipped)
        else:
            logger.info('没有新数据需要插入 (跳过 %d 条重复)', skipped)

        return len(rows), skipped

    def search(self, query_vector: np.ndarray, top_k: int = 5,
               source_filter: str = None) -> List[dict]:
        """向量检索，返回最相似的 top_k 个子块。"""
        try:
            filter_expr = None
            if source_filter:
                filter_expr = f'source_file == "{source_filter}"'

            results = self._client.search(
                self._collection,
                data=[query_vector.tolist()],
                filter=filter_expr,
                limit=top_k,
                output_fields=['chunk_id', 'parent_id', 'content', 'section_title',
                              'page_numbers', 'source_file'],
            )
            hits = []
            for hit in results[0]:
                hits.append({
                    'chunk_id': hit['entity']['chunk_id'],
                    'parent_id': hit['entity']['parent_id'],
                    'content': hit['entity']['content'],
                    'section_title': hit['entity']['section_title'],
                    'page_numbers': hit['entity']['page_numbers'],
                    'source_file': hit['entity'].get('source_file', ''),
                    'score': hit['distance'],
                })
            return hits
        except Exception as e:
            logger.error('Milvus 检索失败: %s', e)
            return []

    def count(self, source_file: str = None) -> int:
        """返回集合中的向量数量。"""
        try:
            if not self._collection_exists():
                return 0
            if source_file:
                results = self._client.query(
                    self._collection,
                    filter=f'source_file == "{source_file}"',
                    output_fields=['chunk_id'],
                    limit=10000,
                )
                return len(results)

            self._client.flush(self._collection)
            get_collection_stats = getattr(self._client, 'get_collection_stats', None)
            if callable(get_collection_stats):
                return self._extract_row_count(get_collection_stats(self._collection))

            conn = getattr(self._client, '_get_connection', lambda: None)()
            if conn and hasattr(conn, 'get_collection_stats'):
                return self._extract_row_count(conn.get_collection_stats(self._collection))
            return 0
        except Exception as e:
            logger.warning('获取集合数量失败: %s', e)
            return 0

    def delete_by_source(self, source_file: str) -> int:
        """删除指定文档来源的所有数据"""
        try:
            if not self._collection_exists():
                return 0
            results = self._client.query(
                self._collection,
                filter=f'source_file == "{source_file}"',
                output_fields=['chunk_id'],
                limit=10000,
            )
            if results:
                ids = [r['chunk_id'] for r in results]
                self._client.delete(self._collection, pks=ids)
                self._client.flush(self._collection)
                logger.info('删除文档 %s 的 %d 条数据', source_file, len(ids))
                return len(ids)
            return 0
        except Exception as e:
            logger.warning('删除文档数据失败: %s', e)
            return 0

    def drop(self) -> None:
        """删除集合。"""
        if self._collection_exists():
            self._client.drop_collection(self._collection)
