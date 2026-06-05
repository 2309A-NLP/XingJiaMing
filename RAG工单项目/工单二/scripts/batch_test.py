"""工单1 - 10个验收问题批量测试 + RAG 评估

工单编号：人工智能 NLP-RAG-基于 PDF 文档的问答系统
"""
import json
import time
import subprocess
import os

API_BASE = "http://localhost:8000"
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

QUESTIONS = [
    {"id": 260, "question": "报告期内，武汉兴图新科电子股份有限公司来自军用领域的收入分别是多少？"},
    {"id": 95, "question": "武汉兴图新科电子股份有限公司参与制定了哪个技术标准？"},
    {"id": 33, "question": "报告期内，武汉兴图新科电子股份有限公司来自军用领域的收入占主营业务收入的比重分别是多少？"},
    {"id": 34, "question": "根据武汉兴图新科电子股份有限公司招股意向书，电子信息行业的上游涉及哪些企业？"},
    {"id": 957, "question": "武汉兴图新科电子股份有限公司在哪个领域已经成为重要供应商？"},
    {"id": 793, "question": "根据武汉兴图新科电子股份有限公司招股意向书，电子信息行业的下游主要包括哪些行业？"},
    {"id": 795, "question": "武汉兴图新科电子股份有限公司参与的哪个工程荣获了国家科技进步一等奖？"},
    {"id": 543, "question": "武汉兴图新科电子股份有限公司注册资本是多少？"},
    {"id": 531, "question": "武汉兴图新科电子股份有限公司法定代表人是谁？"},
    {"id": 207, "question": "武汉兴图新科电子股份有限公司计划使用本次发行募集资金的多少用于补充流动资金？"},
]


def api_post(endpoint, data):
    """用 curl.exe 发 POST 请求，避免 urllib 的连接问题"""
    body = json.dumps(data, ensure_ascii=False)
    tmp_file = os.path.join(PROJECT_DIR, "storage", "_test_body.json")
    with open(tmp_file, "w", encoding="utf-8") as f:
        f.write(body)

    result = subprocess.run(
        ["curl.exe", "-s", "--max-time", "60", "-X", "POST",
         f"{API_BASE}{endpoint}", "-H", "Content-Type: application/json",
         "-d", "@" + tmp_file],
        capture_output=True, text=True, timeout=70
    )
    if result.returncode != 0:
        raise RuntimeError(f'curl failed: {result.stderr}')
    if not result.stdout.strip():
        raise RuntimeError(f'empty response, stderr={result.stderr[:200]}')
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f'invalid json: {result.stdout[:200]}')


def evaluate_rag(rag_answer, llm_answer, sources):
    """RAG 评估：基于来源、答案质量、与LLM差异"""
    scores = {}
    source_count = len(sources)
    scores["source_count"] = source_count
    scores["has_sources"] = source_count > 0
    scores["rag_answer_length"] = len(rag_answer)
    scores["llm_answer_length"] = len(llm_answer)
    scores["rag_has_table"] = "|" in rag_answer and "---" in rag_answer
    scores["rag_has_number"] = any(c.isdigit() for c in rag_answer)

    # RAG vs LLM 差异度
    rag_chars = set(rag_answer)
    llm_chars = set(llm_answer)
    if rag_chars:
        overlap = len(rag_chars & llm_chars) / len(rag_chars | llm_chars)
        scores["answer_similarity"] = round(overlap, 3)
    else:
        scores["answer_similarity"] = 0

    # 综合评分
    score = 0
    if scores["has_sources"]:
        score += 30
    if scores["rag_has_number"]:
        score += 20
    if scores["rag_answer_length"] > 20:
        score += 20
    if scores["rag_has_table"]:
        score += 15
    if scores["answer_similarity"] < 0.7:
        score += 15
    scores["total_score"] = score
    scores["grade"] = "优秀" if score >= 80 else "良好" if score >= 60 else "一般" if score >= 40 else "较差"
    return scores


def main():
    print("=" * 80)
    print("工单1 - RAG 问答系统验收测试")
    print("工单编号：人工智能 NLP-RAG-基于 PDF 文档的问答系统")
    print("=" * 80)

    results = []

    for i, q in enumerate(QUESTIONS):
        print(f"\n{'─' * 60}")
        print(f"[{i+1}/10] ID={q['id']}")
        print(f"问题: {q['question']}")

        try:
            start = time.time()
            compare = api_post("/api/query/compare", {"question": q["question"]})
            elapsed = time.time() - start

            rag_answer = compare["rag_answer"]
            llm_answer = compare["llm_answer"]
            sources = compare["rag_sources"]
            rag_time = compare.get("response_time_ms", int(elapsed * 1000))

            scores = evaluate_rag(rag_answer, llm_answer, sources)

            print(f"RAG: {rag_answer[:100]}")
            print(f"LLM: {llm_answer[:100]}")
            print(f"来源: {len(sources)} | 耗时: {rag_time}ms | 评分: {scores['total_score']} ({scores['grade']})")

            results.append({
                "id": q["id"], "question": q["question"],
                "rag_answer": rag_answer, "llm_answer": llm_answer,
                "rag_sources_count": len(sources), "rag_time_ms": rag_time,
                "evaluation": scores,
            })
            time.sleep(1)

        except Exception as e:
            print(f"错误: {e}")
            results.append({"id": q["id"], "question": q["question"], "error": str(e)})

    # 汇总
    print(f"\n{'=' * 80}")
    print("测试汇总")
    print(f"{'=' * 80}")

    success = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]

    print(f"成功: {len(success)}/10 | 失败: {len(failed)}/10")
    if success:
        avg_time = sum(r["rag_time_ms"] for r in success) / len(success)
        avg_score = sum(r["evaluation"]["total_score"] for r in success) / len(success)
        has_source = sum(1 for r in success if r["rag_sources_count"] > 0)
        print(f"平均响应时间: {avg_time:.0f}ms")
        print(f"平均评分: {avg_score:.1f}/100")
        print(f"有来源的回答: {has_source}/{len(success)}")

        grades = {}
        for r in success:
            g = r["evaluation"]["grade"]
            grades[g] = grades.get(g, 0) + 1
        print(f"评分分布: {grades}")

    output_path = os.path.join(PROJECT_DIR, "docs", "evaluation_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "total": 10, "success": len(success), "failed": len(failed),
                "avg_response_time_ms": round(sum(r.get("rag_time_ms", 0) for r in success) / max(len(success), 1)),
                "avg_score": round(sum(r.get("evaluation", {}).get("total_score", 0) for r in success) / max(len(success), 1), 1),
            },
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到: {output_path}")


if __name__ == "__main__":
    main()





