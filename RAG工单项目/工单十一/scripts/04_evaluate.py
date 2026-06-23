"""
04_evaluate.py — 评估脚本（微调前后对比）
用测试集评估模型检索效果，计算 Recall@K、MRR、NDCG 等指标

用法:
  conda run -n emb python scripts/04_evaluate.py              # 评估微调前
  conda run -n emb python scripts/04_evaluate.py --finetuned  # 评估微调后
  conda run -n emb python scripts/04_evaluate.py --both       # 两个都评估+对比
"""

import json
import sys
import numpy as np
from pathlib import Path
from datetime import datetime

# ============ 配置 ============
PROJECT_DIR = Path(__file__).parent.parent
MODEL_DIR = PROJECT_DIR / "model"
BASE_MODEL = MODEL_DIR / "bge-base-zh-v1.5"
FINETUNED_MODEL = MODEL_DIR / "bge-finetuned"
CHUNKS_FILE = PROJECT_DIR / "data" / "chunks.jsonl"
TEST_FILE = PROJECT_DIR / "data" / "test.jsonl"
RESULTS_DIR = PROJECT_DIR / "results"

TOP_K = 10  # 评估 Recall@10


def load_chunks() -> dict[str, str]:
    """加载所有段落，返回 {chunk_id: text} 映射"""
    chunks = {}
    with open(CHUNKS_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            record = json.loads(line.strip())
            chunks[record['chunk_id']] = record['text']
    return chunks


def load_test_data() -> list[dict]:
    """加载测试集"""
    data = []
    with open(TEST_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            data.append(json.loads(line.strip()))
    return data


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """计算余弦相似度（批量）"""
    a_norm = a / np.linalg.norm(a, axis=1, keepdims=True)
    b_norm = b / np.linalg.norm(b, axis=1, keepdims=True)
    return np.dot(a_norm, b_norm.T)


def evaluate_model(model_path: Path, test_data: list[dict], chunks: dict[str, str], model_name: str) -> dict:
    """评估单个模型"""
    from sentence_transformers import SentenceTransformer

    print(f"\n{'=' * 50}")
    print(f"评估模型: {model_name}")
    print(f"路径: {model_path}")
    print(f"{'=' * 50}")

    # 加载模型
    model = SentenceTransformer(str(model_path))
    model.max_seq_length = 256

    # 编码所有段落（构建向量库）
    print(f"编码 {len(chunks)} 个段落...")
    chunk_ids = list(chunks.keys())
    chunk_texts = [chunks[cid] for cid in chunk_ids]
    chunk_embeddings = model.encode(
        chunk_texts,
        show_progress_bar=True,
        batch_size=32,
    )
    print(f"向量形状: {chunk_embeddings.shape}")

    # 评估每条测试数据
    recalls = []     # Recall@K
    mrrs = []        # MRR
    ndcgs = []       # NDCG@K
    precisions = []  # Precision@K

    print(f"评估 {len(test_data)} 条测试数据...")
    for item in test_data:
        query = item['query']
        relevant_ids = set(item['relevant_ids'])

        # 编码查询
        query_embedding = model.encode([query])

        # 计算相似度
        similarities = cosine_similarity(query_embedding, chunk_embeddings)[0]

        # 取 Top-K
        top_k_indices = np.argsort(similarities)[::-1][:TOP_K]
        top_k_ids = [chunk_ids[i] for i in top_k_indices]

        # 计算指标
        # Recall@K
        hits = sum(1 for rid in relevant_ids if rid in top_k_ids)
        recall = hits / len(relevant_ids) if relevant_ids else 0
        recalls.append(recall)

        # MRR（第一个正确结果的排名倒数）
        rr = 0
        for rank, cid in enumerate(top_k_ids, 1):
            if cid in relevant_ids:
                rr = 1.0 / rank
                break
        mrrs.append(rr)

        # Precision@K
        precision = hits / TOP_K
        precisions.append(precision)

        # NDCG@K
        dcg = 0
        for rank, cid in enumerate(top_k_ids, 1):
            if cid in relevant_ids:
                dcg += 1.0 / np.log2(rank + 1)
        # 理想情况下的 DCG
        ideal_dcg = sum(1.0 / np.log2(i + 2) for i in range(min(len(relevant_ids), TOP_K)))
        ndcg = dcg / ideal_dcg if ideal_dcg > 0 else 0
        ndcgs.append(ndcg)

    # 汇总结果
    results = {
        "model_name": model_name,
        "model_path": str(model_path),
        "test_samples": len(test_data),
        "top_k": TOP_K,
        "recall_at_k": round(np.mean(recalls), 4),
        "mrr": round(np.mean(mrrs), 4),
        "ndcg_at_k": round(np.mean(ndcgs), 4),
        "precision_at_k": round(np.mean(precisions), 4),
        "recall_per_sample": [round(r, 4) for r in recalls],
        "timestamp": datetime.now().isoformat(),
    }

    print(f"\n--- {model_name} 评估结果 ---")
    print(f"  Recall@{TOP_K}:    {results['recall_at_k']}")
    print(f"  MRR:           {results['mrr']}")
    print(f"  NDCG@{TOP_K}:    {results['ndcg_at_k']}")
    print(f"  Precision@{TOP_K}: {results['precision_at_k']}")

    return results


def compare_models(base_results: dict, ft_results: dict) -> dict:
    """对比两个模型的评估结果"""
    print(f"\n{'=' * 50}")
    print("模型对比")
    print(f"{'=' * 50}")

    metrics = ['recall_at_k', 'mrr', 'ndcg_at_k', 'precision_at_k']
    comparison = {"metrics": {}}

    for metric in metrics:
        base_val = base_results[metric]
        ft_val = ft_results[metric]
        improvement = ft_val - base_val
        improvement_pct = (improvement / base_val * 100) if base_val > 0 else 0

        comparison["metrics"][metric] = {
            "base": base_val,
            "finetuned": ft_val,
            "improvement": round(improvement, 4),
            "improvement_pct": round(improvement_pct, 2),
        }

        # 打印对比表
        arrow = "↑" if improvement > 0 else ("↓" if improvement < 0 else "→")
        status = "✅" if improvement > 0 else ("❌" if improvement < 0 else "→")
        print(f"  {metric:20s}: {base_val:.4f} → {ft_val:.4f}  {arrow} {improvement:+.4f} ({improvement_pct:+.1f}%) {status}")

    comparison["conclusion"] = "微调有效" if any(
        comparison["metrics"][m]["improvement"] > 0 for m in metrics
    ) else "微调未带来提升"
    comparison["timestamp"] = datetime.now().isoformat()

    print(f"\n结论: {comparison['conclusion']}")

    return comparison


def main():
    # 解析参数
    args = sys.argv[1:]
    do_both = '--both' in args
    do_finetuned = '--finetuned' in args or do_both

    # 加载数据
    print("加载数据...")
    chunks = load_chunks()
    test_data = load_test_data()
    print(f"段落数: {len(chunks)}")
    print(f"测试样本数: {len(test_data)}")

    if not test_data:
        print("❌ 测试集为空！请先运行 02_generate.py")
        return

    # 确保结果目录存在
    RESULTS_DIR.mkdir(exist_ok=True)

    if do_both:
        # 评估两个模型并对比
        base_results = evaluate_model(BASE_MODEL, test_data, chunks, "原始模型 (baseline)")
        ft_results = evaluate_model(FINETUNED_MODEL, test_data, chunks, "微调后模型")

        # 对比
        comparison = compare_models(base_results, ft_results)

        # 保存结果
        with open(RESULTS_DIR / "baseline.json", 'w', encoding='utf-8') as f:
            json.dump(base_results, f, ensure_ascii=False, indent=2)
        with open(RESULTS_DIR / "finetuned.json", 'w', encoding='utf-8') as f:
            json.dump(ft_results, f, ensure_ascii=False, indent=2)
        with open(RESULTS_DIR / "comparison.json", 'w', encoding='utf-8') as f:
            json.dump(comparison, f, ensure_ascii=False, indent=2)

        print(f"\n结果保存在: {RESULTS_DIR}")

    elif do_finetuned:
        # 只评估微调后
        ft_results = evaluate_model(FINETUNED_MODEL, test_data, chunks, "微调后模型")
        with open(RESULTS_DIR / "finetuned.json", 'w', encoding='utf-8') as f:
            json.dump(ft_results, f, ensure_ascii=False, indent=2)

    else:
        # 只评估原始模型（baseline）
        base_results = evaluate_model(BASE_MODEL, test_data, chunks, "原始模型 (baseline)")
        with open(RESULTS_DIR / "baseline.json", 'w', encoding='utf-8') as f:
            json.dump(base_results, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
