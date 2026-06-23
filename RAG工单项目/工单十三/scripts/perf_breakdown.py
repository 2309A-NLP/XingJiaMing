"""单请求阶段耗时拆解脚本。"""
import json
import os
import time
import urllib.request


API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8013")
QUESTION = os.getenv("PERF_QUESTION", "公司法定代表人是谁？")


def post_json(endpoint: str, payload: dict) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{API_BASE}{endpoint}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    start = time.time()
    result = post_json("/api/query/retrieve", {"question": QUESTION, "top_k": 5, "language": "zh"})
    elapsed_ms = round((time.time() - start) * 1000, 1)
    print("=== Retrieval Breakdown ===")
    print(f"question: {QUESTION}")
    print(f"round_trip_ms: {elapsed_ms}")
    print(f"retrieval_time_ms: {result['retrieval_time_ms']}")
    print(f"total_time_ms: {result['total_time_ms']}")
    print("timings:")
    for key, value in result["timings"].items():
        print(f"  {key}: {value}")
    print(f"sources: {len(result['sources'])}")


if __name__ == "__main__":
    main()
