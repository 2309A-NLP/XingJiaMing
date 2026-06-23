"""
03_mine_neg.py — 挖掘困难负例
用原始模型检索，取排名靠前但不是正例的段落作为困难负例

用法: conda run -n emb python scripts/03_mine_neg.py
"""

import json
import numpy as np
from pathlib import Path
from collections import defaultdict

# ============ 配置 ============
PROJECT_DIR = Path(__file__).parent.parent
MODEL_DIR = PROJECT_DIR / "model"
BASE_MODEL = MODEL_DIR / "bge-base-zh-v1.5"
CHUNKS_FILE = PROJECT_DIR / "data" / "chunks.jsonl"
TRAIN_FILE = PROJECT_DIR / "data" / "train.jsonl"       # 输入：没有负例的训练数据
TRAIN_FINAL = PROJECT_DIR / "data" / "train_final.jsonl" # 输出：完整 triplet
TOP_K = 20  # 从 Top-K 个结果中选困难负例


def load_chunks() -> dict[str, str]:
    """加载所有段落"""
    chunks = {}
    with open(CHUNKS_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            record = json.loads(line.strip())
            chunks[record['chunk_id']] = record['text']
    return chunks


def load_train_data(filepath: Path) -> list[dict]:
    """加载训练数据（只有 anchor + positive，没有 negative）"""
    data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            data.append(json.loads(line.strip()))
    return data


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """计算余弦相似度"""
    a_norm = a / np.linalg.norm(a, axis=1, keepdims=True)
    b_norm = b / np.linalg.norm(b, axis=1, keepdims=True)
    return np.dot(a_norm, b_norm.T)


def main():
    from sentence_transformers import SentenceTransformer

    print("=" * 50)
    print("困难负例挖掘脚本")
    print("=" * 50)

    # 加载数据
    print("\n加载数据...")
    chunks = load_chunks()
    train_data = load_train_data(TRAIN_FILE)
    print(f"段落数: {len(chunks)}")
    print(f"训练数据数: {len(train_data)}")

    if not train_data:
        print("❌ 训练数据为空！请先运行 02_generate.py")
        return

    # 检查是否已经有 negative 字段
    has_negative = all('negative' in r for r in train_data[:10])
    if has_negative:
        print("⚠️ 训练数据已包含负例，跳过挖掘")
        return

    # 加载模型
    print(f"\n加载模型: {BASE_MODEL}")
    model = SentenceTransformer(str(BASE_MODEL))
    model.max_seq_length = 256

    # 编码所有段落
    chunk_ids = list(chunks.keys())
    chunk_texts = [chunks[cid] for cid in chunk_ids]
    positive_id_set = set(r.get('positive_id', '') for r in train_data)

    print(f"编码 {len(chunk_ids)} 个段落...")
    chunk_embeddings = model.encode(
        chunk_texts,
        show_progress_bar=True,
        batch_size=62,
    )

    # 为每个训练样本挖掘困难负例
    print(f"\n为 {len(train_data)} 个样本挖掘困难负例...")
    results = []
    no_hard_neg = 0

    for i, record in enumerate(train_data):
        if (i + 1) % 100 == 0:
            print(f"  进度: {i+1}/{len(train_data)} ({(i+1)/len(train_data)*100:.0f}%)")

        query = record['anchor']
        positive_id = record.get('positive_id', '')

        # 编码查询
        query_emb = model.encode([query])

        # 计算与所有段落的相似度
        sims = cosine_similarity(query_emb, chunk_embeddings)[0]

        # 取 Top-K（排除正例本身）
        top_indices = np.argsort(sims)[::-1]
        hard_negative = None

        for idx in top_indices[:TOP_K]:
            candidate_id = chunk_ids[idx]
            if candidate_id != positive_id:
                # 找到第一个不是正例的高分段落 = 困难负例
                hard_negative = chunk_texts[idx]
                break

        if hard_negative:
            results.append({
                "anchor": query,
                "positive": record['positive'],
                "negative": hard_negative,
                "positive_id": positive_id,
                "source": record.get('source', ''),
            })
        else:
            no_hard_neg += 1
            # 没找到困难负例，用随机负例
            random_idx = np.random.randint(0, len(chunk_texts))
            while chunk_ids[random_idx] == positive_id:
                random_idx = np.random.randint(0, len(chunk_texts))
            results.append({
                "anchor": query,
                "positive": record['positive'],
                "negative": chunk_texts[random_idx],
                "positive_id": positive_id,
                "source": record.get('source', ''),
            })

    # 保存结果
    with open(TRAIN_FINAL, 'w', encoding='utf-8') as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    # 统计
    print(f"\n{'=' * 50}")
    print(f"困难负例挖掘完成！")
    print(f"  成功找到困难负例: {len(results) - no_hard_neg}")
    print(f"  使用随机负例: {no_hard_neg}")
    print(f"  输出文件: {TRAIN_FINAL}")
    print(f"  样本数: {len(results)}")

    # 展示样例
    print(f"\n--- 样例 Triplet ---")
    for i in [0, len(results) // 2, -1]:
        r = results[i]
        print(f"\n  [锚点] {r['anchor']}")
        print(f"  [正例] {r['positive'][:80]}...")
        print(f"  [负例] {r['negative'][:80]}...")


if __name__ == "__main__":
    main()
