"""固定问题集稳态基准脚本。"""
import json
import os
import statistics
import urllib.request
from pathlib import Path


API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8013")
ITERATIONS = int(os.getenv("PERF_ITERATIONS", "20"))
OUT_DIR = Path(os.getenv("PERF_REPORT_DIR", "./docs/perf"))
QUESTIONS = [
    "公司法定代表人是谁？",
    "公司的注册资本是多少？",
    "公司的主营业务是什么？",
    "公司面临哪些经营风险？",
]


def percentile(values, ratio):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * ratio))))
    return ordered[index]


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
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    runs = []
    for _ in range(ITERATIONS):
        for question in QUESTIONS:
            result = post_json("/api/query/retrieve", {"question": question, "top_k": 5, "language": "zh"})
            runs.append(
                {
                    "question": question,
                    "retrieval_time_ms": result["retrieval_time_ms"],
                    "total_time_ms": result["total_time_ms"],
                    "cache_hit": result["cache_hit"],
                }
            )

    totals = [item["total_time_ms"] for item in runs]
    summary = {
        "iterations": ITERATIONS,
        "sample_size": len(runs),
        "avg_total_ms": round(statistics.mean(totals), 1) if totals else 0.0,
        "p50_total_ms": round(percentile(totals, 0.50), 1),
        "p95_total_ms": round(percentile(totals, 0.95), 1),
        "p99_total_ms": round(percentile(totals, 0.99), 1),
        "under_3s_rate": round(sum(1 for x in totals if x <= 3000) / len(totals), 3) if totals else 0.0,
    }

    output = {"summary": summary, "runs": runs}
    output_path = OUT_DIR / "benchmark_results.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"saved: {output_path}")


if __name__ == "__main__":
    main()
