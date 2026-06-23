import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api import cache as cache_module
from api.routes import evaluate as evaluate_module
from api.routes import query as query_module


class StubVectorStore:
    def search(self, query_vector, top_k):
        return [
            {
                "chunk_id": "dense-1",
                "parent_id": "parent-1",
                "content": "武汉力源信息技术股份有限公司的法定代表人为付强。",
                "section_title": "公司基本情况",
                "page_numbers": [1],
                "source_file": "招股说明书1_refined.md",
                "score": 0.95,
            },
            {
                "chunk_id": "dense-2",
                "parent_id": "parent-2",
                "content": "公司注册资本为5520万元。",
                "section_title": "注册资本",
                "page_numbers": [2],
                "source_file": "招股说明书1_refined.md",
                "score": 0.88,
            },
        ][:top_k]


class StubBM25Retriever:
    def search(self, question, top_k, match_mode="standard"):
        return [
            {
                "chunk_id": "sparse-1",
                "parent_id": "parent-3",
                "content": "招股说明书显示公司主营业务覆盖视频通信和智能分析。",
                "section_title": "主营业务",
                "page_numbers": [3],
                "source_file": "招股说明书1_refined.md",
                "score": 12.0,
            }
        ][:top_k]


class StubRetriever:
    def __init__(self):
        self._vs = StubVectorStore()
        self._bm25 = StubBM25Retriever()
        self._reranker = None
        self._reranker_path = None
        self.load_reranker_calls = 0
        self.smart_rerank_calls = 0

    def _load_reranker(self, reranker_type="bge"):
        self.load_reranker_calls += 1

    def _smart_rerank(self, merged, top_k, query):
        self.smart_rerank_calls += 1
        return merged[:top_k]

    def _merge(self, dense, sparse, dense_weight=1.0, sparse_weight=1.5):
        merged = []
        seen = set()
        for item in dense + sparse:
            if item["chunk_id"] in seen:
                continue
            seen.add(item["chunk_id"])
            merged.append(dict(item))
        return merged


class StubEmbedder:
    current_model = "stub-embedding"

    def __init__(self):
        self.encode_calls = 0

    def encode(self, texts):
        self.encode_calls += 1
        return [[0.1, 0.2, 0.3]]

    def switch_model(self, model_name):
        self.current_model = model_name
        return True


class StubGenerator:
    def __init__(self):
        self.generate_calls = 0
        self.stream_calls = 0

    def generate(self, query, contexts, language, history=None):
        self.generate_calls += 1
        return f"回答：{query}"

    def generate_stream(self, query, contexts, language, history=None):
        self.stream_calls += 1
        yield "回答："
        yield query


class StubQueryUnderstanding:
    def analyze(self, question):
        return type(
            "QueryAnalysis",
            (),
            {
                "original_query": question,
                "intent": "factoid",
                "intent_description": "factoid question",
                "disambiguated_query": question,
                "sub_queries": [question],
                "keywords": [],
                "confidence": 0.9,
            },
        )()


class StubSessionMemory:
    def __init__(self):
        self.records = []

    def get_history(self, chat_id):
        if not chat_id:
            return []
        return [{"role": "user", "content": "历史问题"}]

    def add(self, chat_id, role, content):
        self.records.append((chat_id, role, content))


class StubReport:
    total_questions = 3
    avg_precision = 0.91
    avg_recall = 0.83
    avg_response_time_ms = 2410.5
    precision_at_90 = 0.667
    recall_at_95 = 0.333
    response_time_under_3s = 0.667
    category_scores = {"factoid": {"precision": 0.91, "recall": 0.83}}
    latency_p50_ms = 2150.0
    latency_p95_ms = 2980.0
    latency_p99_ms = 3050.0
    under_3s_rate = 0.667
    results = [
        type(
            "EvalResult",
            (),
            {
                "question": "公司法定代表人是谁？",
                "precision": 1.0,
                "recall": 1.0,
                "response_time_ms": 2200.0,
                "keyword_hits": 2,
                "keyword_total": 2,
            },
        )()
    ]


class StubEvaluator:
    def evaluate(self, query_fn, top_k, language):
        return StubReport()


class QueryPerformanceApiTests(unittest.TestCase):
    def setUp(self):
        cache_module._query_cache.clear()
        self.components = {
            "retriever": StubRetriever(),
            "embedder": StubEmbedder(),
            "generator": StubGenerator(),
            "query_understanding": StubQueryUnderstanding(),
        }
        self.session_memory = StubSessionMemory()
        self.app = FastAPI()
        self.app.include_router(query_module.router)
        self.app.include_router(evaluate_module.router)
        self.client = TestClient(self.app)

    def test_retrieve_endpoint_returns_retrieval_metrics(self):
        with patch.object(query_module, "get_components", return_value=self.components), patch.object(
            query_module, "session_mem", self.session_memory
        ):
            response = self.client.post(
                "/query/retrieve",
                json={"question": "公司法定代表人是谁？", "top_k": 2, "language": "zh"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("trace_id", payload)
        self.assertIn("timings", payload)
        self.assertIn("retrieval_time_ms", payload)
        self.assertIn("total_time_ms", payload)
        self.assertIn("cache_hit", payload)
        self.assertFalse(payload["cache_hit"])
        self.assertEqual(len(payload["sources"]), 2)
        self.assertGreaterEqual(payload["retrieval_time_ms"], 0)

    def test_query_marks_cache_hits_and_skips_second_generation(self):
        with patch.object(query_module, "get_components", return_value=self.components), patch.object(
            query_module, "session_mem", self.session_memory
        ):
            first = self.client.post(
                "/query",
                json={"question": "公司法定代表人是谁？", "top_k": 2, "language": "zh"},
            )
            second = self.client.post(
                "/query",
                json={"question": "公司法定代表人是谁？", "top_k": 2, "language": "zh"},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        first_payload = first.json()
        second_payload = second.json()
        self.assertIn("trace_id", first_payload)
        self.assertIn("timings", first_payload)
        self.assertIn("cache_hit", first_payload)
        self.assertFalse(first_payload["cache_hit"])
        self.assertTrue(second_payload["cache_hit"])
        self.assertEqual(self.components["generator"].generate_calls, 1)

    def test_stream_done_event_includes_metrics_and_no_lightrag_tail(self):
        with patch.object(query_module, "get_components", return_value=self.components), patch.object(
            query_module, "session_mem", self.session_memory
        ):
            response = self.client.post(
                "/query/stream",
                json={"question": "公司法定代表人是谁？", "top_k": 2, "language": "zh"},
            )

        self.assertEqual(response.status_code, 200)
        raw_events = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
        parsed = [json.loads(item) for item in raw_events]
        event_types = [item["type"] for item in parsed]
        self.assertIn("sources", event_types)
        self.assertIn("config", event_types)
        self.assertIn("done", event_types)
        self.assertNotIn("lightrag_result", event_types)

        done_event = next(item for item in parsed if item["type"] == "done")
        self.assertIn("trace_id", done_event["data"])
        self.assertIn("timings", done_event["data"])
        self.assertIn("retrieval_time_ms", done_event["data"])
        self.assertIn("total_time_ms", done_event["data"])

    def test_evaluate_returns_latency_percentiles(self):
        with patch.object(evaluate_module, "get_components", return_value=self.components), patch(
            "scripts.pipeline.rag_evaluator.RAGEvaluator", StubEvaluator
        ):
            response = self.client.post("/evaluate", json={"top_k": 3, "search_mode": "hybrid"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("p50_response_time_ms", payload)
        self.assertIn("p95_response_time_ms", payload)
        self.assertIn("p99_response_time_ms", payload)
        self.assertIn("under_3s_rate", payload)
        self.assertEqual(payload["p95_response_time_ms"], 2980.0)


if __name__ == "__main__":
    unittest.main()
