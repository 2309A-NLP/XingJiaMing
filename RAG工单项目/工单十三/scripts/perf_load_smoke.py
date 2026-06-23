"""轻量并发压测骨架。"""
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import urllib.request


API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8013")
CONCURRENCY = int(os.getenv("PERF_CONCURRENCY", "5"))
REQUESTS = int(os.getenv("PERF_REQUESTS", "20"))
OUT_DIR = Path(os.getenv("PERF_REPORT_DIR", "./docs/perf"))
QUESTION = os.getenv("PERF_QUESTION", "公司的主营业务是什么？")


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


def one_call(index: int) -> dict:
    result = post_json("/api/query/retrieve", {"question": QUESTION, "top_k": 5, "language": "zh"})
    return {"index": index, "total_time_ms": result["total_time_ms"], "retrieval_time_ms": result["retrieval_time_ms"]}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = [executor.submit(one_call, i) for i in range(REQUESTS)]
        for future in as_completed(futures):
            records.append(future.result())

    records.sort(key=lambda item: item["index"])
    output_path = OUT_DIR / "load_smoke_results.json"
    output_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {output_path}")


if __name__ == "__main__":
    main()
