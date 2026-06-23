import os
import sys
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
import threading
import time
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api import init as init_module
from api.init import _warm_up_components
import scripts.memory.session_memory as session_memory_module
import scripts.pipeline.bm25_retriever as bm25_module
import scripts.pipeline.chunker as chunker_module
import scripts.pipeline.embedder as embedder_module
import scripts.pipeline.llm_generator as generator_module
import scripts.pipeline.query_understanding as query_understanding_module
import scripts.pipeline.retriever as retriever_module
import scripts.pipeline.vector_store as vector_store_module
import scripts.pipeline.vision_analyzer as vision_analyzer_module
from scripts.pipeline.llm_generator import Generator
from scripts.pipeline.query_understanding import QueryUnderstanding
from scripts.pipeline.rag_evaluator import RAGEvaluator, TestCase
from scripts.pipeline.reranker import BGEReranker
from scripts.pipeline.retriever import Retriever
from scripts.pipeline.vector_store import VectorStore


class RecordingReranker:
    def __init__(self, device=None):
        self.calls = []
        self._device = device

    @property
    def name(self):
        return "recording"

    def rerank(self, query, candidates, top_k=5):
        self.calls.append({"query": query, "candidate_count": len(candidates), "top_k": top_k})
        return candidates[:top_k]


class FakeTensor:
    def __init__(self, values):
        self._values = values

    def view(self, *_args, **_kwargs):
        return self

    def detach(self):
        return self

    def cpu(self):
        return self

    def tolist(self):
        return list(self._values)


class FakeBatch(dict):
    def to(self, _device):
        return self


class FakeTokenizer:
    def __init__(self):
        self.calls = []

    def __call__(self, pairs, **kwargs):
        self.calls.append({"pairs": pairs, "kwargs": kwargs})
        return FakeBatch({"pairs": pairs})


class FakeModel:
    def __init__(self, scores):
        self._scores = scores
        self.calls = []

    def __call__(self, **inputs):
        self.calls.append(inputs)
        return type("Output", (), {"logits": FakeTensor(self._scores)})()


@contextmanager
def _fake_no_grad():
    yield


class RecordingBM25:
    def __init__(self):
        self.calls = []

    def search(self, query, top_k, match_mode="standard"):
        self.calls.append({"query": query, "top_k": top_k, "match_mode": match_mode})
        return []


class RecordingEmbedder:
    def __init__(self):
        self.calls = []

    def encode(self, texts):
        self.calls.append(list(texts))
        return [[0.1, 0.2, 0.3]]


class RecordingGenerator:
    def __init__(self):
        self.calls = []

    def _build_messages(self, prompt, user_prompt, history=None):
        self.calls.append(
            {"prompt": prompt, "user_prompt": user_prompt, "history": history or []}
        )
        return []


class RecordingRerankEngine:
    def __init__(self):
        self.calls = []

    @property
    def name(self):
        return "recording"

    def rerank(self, query, candidates, top_k=5):
        self.calls.append(
            {"query": query, "candidate_count": len(candidates), "top_k": top_k}
        )
        return candidates[:top_k]


class CollectionAwareClient:
    def __init__(self, collections=None):
        self._collections = collections or []

    def list_collections(self):
        return list(self._collections)


class ExplicitHasCollectionClient:
    def __init__(self, has_collection):
        self._has_collection = has_collection

    def has_collection(self, _name):
        return self._has_collection


class FakeSchema:
    def __init__(self):
        self.fields = []
        self.verified = False

    def add_field(self, name, dtype, **kwargs):
        self.fields.append({"name": name, "dtype": dtype, "kwargs": kwargs})

    def verify(self):
        self.verified = True


class FakeConnection:
    def __init__(self, stats=None):
        self.create_calls = []
        self.stats = stats or []

    def create_collection(self, collection_name, schema, **kwargs):
        self.create_calls.append(
            {"collection_name": collection_name, "schema": schema, "kwargs": kwargs}
        )

    def get_collection_stats(self, _collection_name):
        return self.stats


class CompatMilvusClient:
    def __init__(self, stats=None):
        self.schema = FakeSchema()
        self.connection = FakeConnection(stats=stats)
        self.prepare_calls = []
        self.index_calls = []
        self.load_calls = []
        self.query_results = []
        self.delete_calls = []

    def has_collection(self, _name):
        return False

    def create_schema(self, **kwargs):
        self.create_schema_kwargs = kwargs
        return self.schema

    def prepare_index_params(
        self,
        field_name,
        index_type=None,
        metric_type=None,
        index_name="",
        params=None,
        **kwargs,
    ):
        payload = {
            "field_name": field_name,
            "index_type": index_type,
            "metric_type": metric_type,
            "index_name": index_name,
            "params": params or {},
        }
        payload.update(kwargs)
        self.prepare_calls.append(payload)
        return payload

    def _get_connection(self):
        return self.connection

    def _create_index(self, collection_name, field_name, index_params, timeout=None):
        self.index_calls.append(
            {
                "collection_name": collection_name,
                "field_name": field_name,
                "index_params": index_params,
                "timeout": timeout,
            }
        )

    def _load(self, collection_name, timeout=None):
        self.load_calls.append(
            {"collection_name": collection_name, "timeout": timeout}
        )

    def flush(self, _collection_name):
        return None

    def query(self, _collection_name, filter, output_fields=None, **kwargs):
        self.query_calls = {
            "filter": filter,
            "output_fields": output_fields,
            "kwargs": kwargs,
        }
        return list(self.query_results)

    def delete(self, collection_name, pks=None, timeout=None, filter="", **kwargs):
        self.delete_calls.append(
            {
                "collection_name": collection_name,
                "pks": pks,
                "timeout": timeout,
                "filter": filter,
                "kwargs": kwargs,
            }
        )


class FakeRedisClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def ping(self):
        return True


class FakeRerankerModel:
    def __init__(self):
        self.to_calls = []

    def to(self, device):
        self.to_calls.append(device)
        return self

    def eval(self):
        return self


class FakeAutoTokenizer:
    @classmethod
    def from_pretrained(cls, _model_path):
        return object()


class FakeAutoModelForSequenceClassification:
    @classmethod
    def from_pretrained(cls, _model_path):
        return FakeRerankerModel()


class PipelineOptimizationTests(unittest.TestCase):
    def test_get_components_initializes_only_once_under_concurrency(self):
        class SlowEmbedder:
            instances = 0

            def __init__(self, *args, **kwargs):
                type(self).instances += 1
                time.sleep(0.2)
                self.dim = 3

            def encode(self, texts):
                return [[0.1, 0.2, 0.3] for _ in texts]

        class StubStore:
            def __init__(self, *args, **kwargs):
                pass

            def create(self, dim):
                self.dim = dim

            def count(self):
                return 0

        class StubBM25:
            def __init__(self, children):
                self.children = children

        class StubRetriever:
            def __init__(self, *args, **kwargs):
                pass

        class StubGenerator:
            def __init__(self, *args, **kwargs):
                pass

        class StubQueryUnderstanding:
            def __init__(self, *args, **kwargs):
                pass

        class StubChunker:
            def __init__(self, *args, **kwargs):
                pass

        class StubVisionAnalyzer:
            is_available = False

            def __init__(self, *args, **kwargs):
                pass

        init_module._components.clear()

        results = []
        errors = []

        def worker():
            try:
                results.append(init_module.get_components())
            except Exception as exc:
                errors.append(exc)

        with patch.dict(
            os.environ,
            {
                "EMBEDDING_MODEL_PATH": "fake-embedder",
                "MILVUS_HOST": "127.0.0.1",
                "MILVUS_PORT": "19530",
                "MILVUS_COLLECTION": "rag_workorder13",
                "DATA_DIR": str(PROJECT_ROOT / "data"),
                "RERANK_ENABLED": "false",
                "VISION_ENABLED": "false",
            },
            clear=False,
        ), patch.object(embedder_module, "Embedder", SlowEmbedder), patch.object(
            vector_store_module, "VectorStore", StubStore
        ), patch.object(bm25_module, "BM25Retriever", StubBM25), patch.object(
            retriever_module, "Retriever", StubRetriever
        ), patch.object(generator_module, "Generator", StubGenerator), patch.object(
            query_understanding_module, "QueryUnderstanding", StubQueryUnderstanding
        ), patch.object(chunker_module, "Chunker", StubChunker), patch.object(
            vision_analyzer_module, "VisionAnalyzer", StubVisionAnalyzer
        ), patch.object(init_module, "_load_all_documents", return_value=([], [])), patch.object(
            init_module, "_warm_up_components", lambda _components: None
        ):
            threads = [threading.Thread(target=worker) for _ in range(3)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertFalse(errors)
        self.assertEqual(SlowEmbedder.instances, 1)
        self.assertEqual(len(results), 3)
        self.assertTrue(all(result is results[0] for result in results))

    def test_smart_rerank_limits_candidate_pool(self):
        reranker = RecordingReranker()
        retriever = Retriever(vector_store=None, bm25_retriever=None, embedder=None, reranker=reranker)

        merged = []
        for idx in range(24):
            merged.append(
                {
                    "chunk_id": f"chunk-{idx}",
                    "content": f"内容 {idx}",
                    "hit_count": 1,
                }
            )

        result = retriever._smart_rerank(merged, top_k=5, query="公司法定代表人是谁？")

        self.assertEqual(len(result), 5)
        self.assertEqual(len(reranker.calls), 1)
        self.assertEqual(reranker.calls[0]["candidate_count"], 12)

    def test_smart_rerank_uses_smaller_cpu_candidate_pool(self):
        reranker = RecordingReranker(device="cpu")
        with patch.dict(os.environ, {"RERANK_CANDIDATE_K_CPU": "6"}, clear=False):
            retriever = Retriever(
                vector_store=None,
                bm25_retriever=None,
                embedder=None,
                reranker=reranker,
            )

        merged = []
        for idx in range(24):
            merged.append(
                {
                    "chunk_id": f"chunk-{idx}",
                    "content": f"内容 {idx}",
                    "hit_count": 1,
                }
            )

        result = retriever._smart_rerank(merged, top_k=5, query="公司的注册资本是多少？")

        self.assertEqual(len(result), 5)
        self.assertEqual(len(reranker.calls), 1)
        self.assertEqual(reranker.calls[0]["candidate_count"], 6)

    def test_generator_context_builder_caps_total_context_chars(self):
        generator = Generator.__new__(Generator)
        generator._max_context_chars = 120

        contexts = []
        for idx in range(4):
            contexts.append(
                type(
                    "Ctx",
                    (),
                    {
                        "content": "内容" * 40,
                        "metadata": {
                            "section_title": f"章节{idx}",
                            "source_file": "招股说明书1_refined.md",
                        },
                    },
                )()
            )

        context_text = generator._build_context(contexts)
        self.assertLessEqual(len(context_text), 220)
        self.assertIn("【资料1", context_text)
        self.assertNotIn("【资料4", context_text)

    def test_bge_reranker_batches_candidates_in_one_model_call(self):
        reranker = BGEReranker.__new__(BGEReranker)
        reranker._device = "cpu"
        reranker._tokenizer = FakeTokenizer()
        reranker._model = FakeModel([0.2, 0.9, 0.5])

        candidates = [
            {"chunk_id": "chunk-1", "content": "第一段内容"},
            {"chunk_id": "chunk-2", "content": "第二段内容"},
            {"chunk_id": "chunk-3", "content": "第三段内容"},
        ]
        fake_torch = types.SimpleNamespace(no_grad=_fake_no_grad)

        with patch.dict(sys.modules, {"torch": fake_torch}):
            result = reranker.rerank("谁是法定代表人", candidates, top_k=2)

        self.assertEqual(len(reranker._tokenizer.calls), 1)
        self.assertEqual(len(reranker._model.calls), 1)
        self.assertEqual([item["chunk_id"] for item in result], ["chunk-2", "chunk-3"])
        self.assertEqual(result[0]["rerank_score"], 0.9)
        self.assertEqual(result[1]["rerank_score"], 0.5)

    def test_generator_constructor_tolerates_missing_api_key(self):
        with patch.dict(os.environ, {"MIMO_API_KEY": ""}, clear=False):
            generator = Generator()

        self.assertIsNone(generator._client)
        with self.assertRaises(RuntimeError):
            generator.generate("问题", [], "zh")

    def test_query_understanding_falls_back_without_api_key(self):
        with patch.dict(os.environ, {"MIMO_API_KEY": ""}, clear=False):
            analyzer = QueryUnderstanding()

        result = analyzer.analyze("公司的主营业务是什么？")
        self.assertEqual(result.original_query, "公司的主营业务是什么？")
        self.assertEqual(result.disambiguated_query, "公司的主营业务是什么？")
        self.assertEqual(result.sub_queries, ["公司的主营业务是什么？"])

    def test_evaluator_computes_latency_percentiles_and_under_3s_rate(self):
        cases = [
            TestCase(question="q1", expected_keywords=["A"]),
            TestCase(question="q2", expected_keywords=["A"]),
            TestCase(question="q3", expected_keywords=["A"]),
            TestCase(question="q4", expected_keywords=["A"]),
            TestCase(question="q5", expected_keywords=["A"]),
        ]
        latencies = iter([1000, 1500, 2000, 2500, 4000])

        def query_fn(question, top_k, language):
            return f"answer {question} A", [{"source_file": "doc.md"}], next(latencies)

        report = RAGEvaluator(test_cases=cases).evaluate(query_fn, top_k=5, language="zh")

        self.assertEqual(report.p50_response_time_ms, 2000.0)
        self.assertEqual(report.p95_response_time_ms, 4000.0)
        self.assertEqual(report.p99_response_time_ms, 4000.0)
        self.assertEqual(report.under_3s_rate, 0.8)

    def test_warm_up_components_hits_embedder_bm25_reranker_and_generator(self):
        embedder = RecordingEmbedder()
        bm25 = RecordingBM25()
        reranker = RecordingRerankEngine()
        generator = RecordingGenerator()
        retriever = type(
            "RetrieverStub",
            (),
            {
                "_bm25": bm25,
                "_reranker": reranker,
                "_smart_rerank": lambda self, merged, top_k, query: reranker.rerank(
                    query, merged, top_k
                ),
            },
        )()

        _warm_up_components(
            {
                "embedder": embedder,
                "bm25": bm25,
                "retriever": retriever,
                "generator": generator,
            }
        )

        self.assertEqual(embedder.calls, [["warmup"]])
        self.assertEqual(len(bm25.calls), 1)
        self.assertEqual(len(reranker.calls), 1)
        self.assertEqual(len(generator.calls), 1)

    def test_vector_store_collection_exists_supports_list_collections_fallback(self):
        store = VectorStore.__new__(VectorStore)
        store._collection = "rag_workorder13"
        store._client = CollectionAwareClient(["rag_workorder13", "other"])

        self.assertTrue(store._collection_exists())

    def test_vector_store_collection_exists_prefers_native_has_collection(self):
        store = VectorStore.__new__(VectorStore)
        store._collection = "rag_workorder13"
        store._client = ExplicitHasCollectionClient(True)

        self.assertTrue(store._collection_exists())

    def test_vector_store_create_uses_schema_connection_for_milvus_compat(self):
        store = VectorStore.__new__(VectorStore)
        store._collection = "rag_workorder13"
        store._client = CompatMilvusClient()

        store.create(dim=3)

        self.assertEqual(store._client.create_schema_kwargs, {"auto_id": False, "enable_dynamic_field": True})
        self.assertEqual(store._client.prepare_calls[0]["field_name"], "vector")
        self.assertEqual(store._client.prepare_calls[0]["metric_type"], "COSINE")
        self.assertTrue(store._client.schema.verified)
        self.assertEqual(len(store._client.connection.create_calls), 1)
        self.assertEqual(
            store._client.connection.create_calls[0]["collection_name"], "rag_workorder13"
        )
        self.assertEqual(
            store._client.connection.create_calls[0]["kwargs"]["consistency_level"],
            "Strong",
        )
        self.assertEqual(store._client.index_calls[0]["field_name"], "vector")
        self.assertEqual(store._client.load_calls[0]["collection_name"], "rag_workorder13")

    def test_vector_store_count_falls_back_to_connection_stats(self):
        store = VectorStore.__new__(VectorStore)
        store._collection = "rag_workorder13"
        store._client = CompatMilvusClient(stats=[{"key": "row_count", "value": "7"}])
        store._client.has_collection = lambda _name: True

        self.assertEqual(store.count(), 7)

    def test_vector_store_delete_by_source_uses_pks_argument(self):
        store = VectorStore.__new__(VectorStore)
        store._collection = "rag_workorder13"
        store._client = CompatMilvusClient()
        store._client.has_collection = lambda _name: True
        store._client.query_results = [{"chunk_id": "chunk-a"}, {"chunk_id": "chunk-b"}]

        deleted = store.delete_by_source("doc.md")

        self.assertEqual(deleted, 2)
        self.assertEqual(store._client.delete_calls[0]["pks"], ["chunk-a", "chunk-b"])
        self.assertNotIn("ids", store._client.delete_calls[0]["kwargs"])

    def test_session_memory_uses_env_driven_redis_password(self):
        fake_redis_module = types.SimpleNamespace(Redis=lambda **kwargs: FakeRedisClient(**kwargs))

        with patch.dict(
            os.environ,
            {
                "REDIS_HOST": "127.0.0.1",
                "REDIS_PORT": "6379",
                "REDIS_PASSWORD": "infini_rag_flow",
                "REDIS_DB": "2",
            },
            clear=False,
        ), patch.dict(sys.modules, {"redis": fake_redis_module}):
            memory = session_memory_module.SessionMemory()

        self.assertIsNotNone(memory._r)
        self.assertEqual(memory._r.kwargs["host"], "127.0.0.1")
        self.assertEqual(memory._r.kwargs["port"], 6379)
        self.assertEqual(memory._r.kwargs["password"], "infini_rag_flow")
        self.assertEqual(memory._r.kwargs["db"], 2)
        self.assertTrue(memory._r.kwargs["decode_responses"])

    def test_bge_reranker_falls_back_to_cpu_when_cuda_unavailable(self):
        fake_torch = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False))
        fake_transformers = types.SimpleNamespace(
            AutoTokenizer=FakeAutoTokenizer,
            AutoModelForSequenceClassification=FakeAutoModelForSequenceClassification,
        )

        with patch.dict(sys.modules, {"torch": fake_torch, "transformers": fake_transformers}):
            reranker = BGEReranker(model_path="fake-model", device="cuda")

        self.assertEqual(reranker._device, "cpu")
        self.assertEqual(reranker._model.to_calls, ["cpu"])


if __name__ == "__main__":
    unittest.main()
