"""工单十二 RAG vs LightRAG 评估脚本

15道测试问题，分别用传统RAG和LightRAG检索，
输出RAGAS评估指标对比。
"""
from __future__ import annotations
import json
import logging
import os
import sys
import time
from pathlib import Path

# 确保项目根目录在路径中
_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))

# WSL环境: 转换Windows路径 + 修正Milvus主机
def _to_wsl_path(win_path: str) -> str:
    if win_path and len(win_path) >= 2 and win_path[1] == ':':
        drive = win_path[0].lower()
        rest = win_path[2:].replace('\\', '/')
        return f'/mnt/{drive}{rest}'
    return win_path

from dotenv import load_dotenv
load_dotenv(override=True)

# 转换路径
for key in ['EMBEDDING_MODEL_PATH', 'RERANK_MODEL_PATH']:
    val = os.getenv(key, '')
    if val and ':' in val:
        os.environ[key] = _to_wsl_path(val)
models_str = os.getenv('EMBEDDING_MODELS', '')
if models_str and ':' in models_str:
    parts = models_str.split(',')
    converted = []
    for p in parts:
        name, path = p.split(':', 1)
        converted.append(f'{name}:{_to_wsl_path(path)}')
    os.environ['EMBEDDING_MODELS'] = ','.join(converted)

# WSL访问Windows Docker用172.19.112.1
os.environ['MILVUS_HOST'] = '172.19.112.1'
os.environ['no_proxy'] = '*'
os.environ['NO_PROXY'] = '*'
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# 15 道测试问题
# ══════════════════════════════════════════════════════════════

TEST_QUESTIONS = [
    # 武汉力源信息技术股份有限公司
    {"id": 5, "question": "武汉力源信息技术股份有限公司组织结构图中，销售部有几个部门构成，其中大客户销售部有几个销售处构成？"},
    {"id": 6, "question": "武汉力源信息技术股份有限公司招股意向书中，从2008年中国IC市场应用结构与增长图中可以看出，增长率最快的是哪个行业？负增长的是哪个行业？"},
    {"id": 1, "question": "武汉力源信息技术股份有限公司本次发行股数是多少，占发行后总股本的比例是多少？"},
    {"id": 2, "question": "武汉力源信息技术股份有限公司本次募集资金拟投资哪些项目？"},
    {"id": 3, "question": "与武汉力源信息技术股份有限公司存在控制关系的关联方是谁，持股比例和本公司关系是什么？"},
    {"id": 4, "question": "与武汉力源信息技术股份有限公司不存在控制关系的关联方企业有哪些？"},
    # 武汉兴图新科电子股份有限公司
    {"id": 260, "question": "报告期内，武汉兴图新科电子股份有限公司来自军用领域的收入分别是多少？"},
    {"id": 95, "question": "武汉兴图新科电子股份有限公司参与制定了哪个技术标准？"},
    {"id": 33, "question": "报告期内，武汉兴图新科电子股份有限公司来自军用领域的收入占主营业务收入的比重分别是多少？"},
    {"id": 34, "question": "根据武汉兴图新科电子股份有限公司招股意向书，电子信息行业的上游涉及哪些企业？"},
    {"id": 957, "question": "武汉兴图新科电子股份有限公司在哪个领域已经成为重要供应商？"},
    {"id": 793, "question": "根据武汉兴图新科电子股份有限公司招股意向书，电子信息行业的下游主要包括哪些行业？"},
    {"id": 795, "question": "武汉兴图新科电子股份有限公司参与的哪个工程荣获了国家科技进步一等奖？"},
    {"id": 543, "question": "武汉兴图新科电子股份有限公司注册资本是多少？"},
    {"id": 531, "question": "武汉兴图新科电子股份有限公司法定代表人是谁？"},
]


def run_traditional_rag(question: str) -> dict:
    """用传统RAG检索（直接连Milvus，绕过api.init）"""
    try:
        from scripts.pipeline.embedder import Embedder
        from scripts.pipeline.vector_store import VectorStore
        from scripts.pipeline.llm_generator import Generator

        # 单例缓存
        if not hasattr(run_traditional_rag, '_embedder'):
            run_traditional_rag._embedder = Embedder(model_path='/mnt/e/AI_models/BGE-M3')
            run_traditional_rag._store = VectorStore(host='172.19.112.1', port=19530, collection='rag_workorder6')
            run_traditional_rag._generator = Generator()

        embedder = run_traditional_rag._embedder
        store = run_traditional_rag._store
        generator = run_traditional_rag._generator

        t0 = time.time()
        q_vec = embedder.encode([question])[0]
        results = store.search(q_vec, top_k=10)
        answer = generator.generate(query=question, contexts=results)
        contexts = [r.get('content', '') for r in results]
        elapsed = time.time() - t0

        return {
            "answer": answer,
            "contexts": contexts,
            "time": round(elapsed, 2),
            "error": None,
        }
    except Exception as e:
        return {"answer": "", "contexts": [], "time": 0, "error": str(e)}


def run_lightrag(question: str, loop=None) -> dict:
    """用LightRAG检索"""
    try:
        import asyncio
        from scripts.pipeline.lightrag_service import aquery_lightrag
        t0 = time.time()
        if loop:
            answer = loop.run_until_complete(aquery_lightrag(question=question, mode="hybrid"))
        else:
            answer = asyncio.run(aquery_lightrag(question=question, mode="hybrid"))
        elapsed = time.time() - t0

        return {
            "answer": answer or "",
            "time": round(elapsed, 2),
            "error": None,
        }
    except Exception as e:
        return {"answer": "", "time": 0, "error": str(e)}


def build_ragas_dataset(results: list[dict]) -> dict:
    """构建RAGAS评估数据集格式"""
    dataset = {
        "question": [],
        "answer_rag": [],
        "answer_lightrag": [],
        "contexts_rag": [],
        "contexts_lightrag": [],
        "ground_truth": [],  # 需要手动填写或用LLM生成
    }
    for r in results:
        dataset["question"].append(r["question"])
        dataset["answer_rag"].append(r["rag"]["answer"])
        dataset["answer_lightrag"].append(r["lightrag"]["answer"])
        dataset["contexts_rag"].append(r["rag"].get("contexts", []))
        dataset["contexts_lightrag"].append(r["lightrag"].get("contexts", []))
        dataset["ground_truth"].append("")  # 待补充
    return dataset


def main():
    """运行评估"""
    import asyncio

    logger.info("=" * 60)
    logger.info("工单十二：RAG vs LightRAG 对比评估")
    logger.info("=" * 60)

    # 创建单个event loop用于所有LightRAG查询
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    results = []

    for i, item in enumerate(TEST_QUESTIONS):
        qid = item["id"]
        question = item["question"]
        logger.info("\n[%d/%d] Q%d: %s", i+1, len(TEST_QUESTIONS), qid, question[:50] + "...")

        # 传统RAG
        logger.info("  传统RAG 检索中...")
        rag_result = run_traditional_rag(question)
        if rag_result["error"]:
            logger.warning("  RAG 错误: %s", rag_result["error"])
        else:
            logger.info("  RAG 完成 (%.2fs): %s...", rag_result["time"], rag_result["answer"][:80])

        # LightRAG (复用同一个event loop)
        logger.info("  LightRAG 检索中...")
        lightrag_result = run_lightrag(question, loop=loop)
        if lightrag_result["error"]:
            logger.warning("  LightRAG 错误: %s", lightrag_result["error"])
        else:
            logger.info("  LightRAG 完成 (%.2fs): %s...", lightrag_result["time"], lightrag_result["answer"][:80])

        results.append({
            "id": qid,
            "question": question,
            "rag": rag_result,
            "lightrag": lightrag_result,
        })

    # 保存结果
    output_dir = Path(_project_root) / "docs"
    output_dir.mkdir(exist_ok=True)

    # 原始结果
    raw_path = output_dir / "lightrag_comparison_results.json"
    with open(raw_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info("\n原始结果已保存: %s", raw_path)

    # 生成对比报告
    report = generate_report(results)
    report_path = output_dir / "lightrag_comparison_report.md"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    logger.info("对比报告已保存: %s", report_path)

    # 打印摘要
    print("\n" + "=" * 60)
    print("评估完成！")
    print(f"  总问题数: {len(results)}")
    rag_errors = sum(1 for r in results if r['rag']['error'])
    lightrag_errors = sum(1 for r in results if r['lightrag']['error'])
    print(f"  传统RAG错误: {rag_errors}")
    print(f"  LightRAG错误: {lightrag_errors}")
    rag_avg_time = sum(r['rag']['time'] for r in results) / len(results)
    lightrag_avg_time = sum(r['lightrag']['time'] for r in results) / len(results)
    print(f"  传统RAG平均耗时: {rag_avg_time:.2f}s")
    print(f"  LightRAG平均耗时: {lightrag_avg_time:.2f}s")
    print("=" * 60)


def generate_report(results: list[dict]) -> str:
    """生成Markdown对比报告"""
    lines = [
        "# 工单十二：RAG vs LightRAG 对比评估报告\n",
        "## 概述\n",
        "基于两份招股说明书，对比传统RAG（向量+BM25）和LightRAG（知识图谱+向量）的检索效果。\n",
        "## 评估结果\n",
        "| ID | 问题 | 传统RAG耗时 | LightRAG耗时 | 传统RAG回答 | LightRAG回答 |",
        "|---|---|---|---|---|---|",
    ]

    for r in results:
        q = r["question"][:30] + "..." if len(r["question"]) > 30 else r["question"]
        rag_time = f"{r['rag']['time']:.2f}s" if not r['rag']['error'] else f"❌ {r['rag']['error'][:20]}"
        lt_time = f"{r['lightrag']['time']:.2f}s" if not r['lightrag']['error'] else f"❌ {r['lightrag']['error'][:20]}"
        rag_ans = (r['rag']['answer'][:50] + "...") if r['rag']['answer'] else "无结果"
        lt_ans = (r['lightrag']['answer'][:50] + "...") if r['lightrag']['answer'] else "无结果"
        lines.append(f"| {r['id']} | {q} | {rag_time} | {lt_time} | {rag_ans} | {lt_ans} |")

    # 统计
    rag_errors = sum(1 for r in results if r['rag']['error'])
    lt_errors = sum(1 for r in results if r['lightrag']['error'])
    rag_avg = sum(r['rag']['time'] for r in results) / len(results)
    lt_avg = sum(r['lightrag']['time'] for r in results) / len(results)

    lines.extend([
        "\n## 统计摘要\n",
        f"- 传统RAG错误数: {rag_errors}/{len(results)}",
        f"- LightRAG错误数: {lt_errors}/{len(results)}",
        f"- 传统RAG平均耗时: {rag_avg:.2f}s",
        f"- LightRAG平均耗时: {lt_avg:.2f}s",
        "\n## 详细回答对比\n",
    ])

    for r in results:
        lines.append(f"### Q{r['id']}: {r['question']}\n")
        lines.append(f"**传统RAG:**\n{r['rag']['answer'] or '无结果'}\n")
        lines.append(f"**LightRAG:**\n{r['lightrag']['answer'] or '无结果'}\n")
        lines.append("---\n")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
