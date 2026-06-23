"""
05_train.py — Embedding 模型微调脚本
使用 sentence-transformers + TripletLoss 微调 bge-base-zh-v1.5

用法: conda run -n emb python scripts/05_train.py
"""

import json
import os
from pathlib import Path
from datetime import datetime

# ============ 配置 ============
PROJECT_DIR = Path(__file__).parent.parent
MODEL_DIR = PROJECT_DIR / "model"
BASE_MODEL = MODEL_DIR / "bge-base-zh-v1.5"          # 原始模型
FINETUNED_MODEL = MODEL_DIR / "bge-finetuned"         # 微调后保存位置
TRAIN_FILE = PROJECT_DIR / "data" / "train_final.jsonl"  # 训练集（完整triplet，由03生成）
RESULTS_DIR = PROJECT_DIR / "results"

# 训练参数
EPOCHS = 1                # 训练轮数（先1轮试效果）
BATCH_SIZE = 16           # 每批次样本数
LEARNING_RATE = 5e-6      # 学习率（降低，防坍塌）
WARMUP_RATIO = 0.1        # 预热比例
MAX_SEQ_LENGTH = 128      # 最大序列长度（token数）
EVAL_STEPS = 50           # 每50步打印一次loss
MARGIN = 0.3              # 降低margin


def load_triplet_data(filepath: Path) -> list[dict]:
    """加载训练数据（支持 triplet 和 pair 两种格式）"""
    data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            record = json.loads(line.strip())
            # 只需要 anchor 和 positive
            if 'anchor' in record and 'positive' in record:
                data.append(record)
    return data


def main():
    print("=" * 50)
    print("Embedding 模型微调脚本")
    print("=" * 50)

    # 检查依赖
    try:
        import torch
        from sentence_transformers import SentenceTransformer
        from sentence_transformers import losses
        from sentence_transformers import InputExample
    except ImportError as e:
        print(f"❌ 缺少依赖: {e}")
        print("请运行: conda activate emb && pip install sentence-transformers torch")
        return

    # 检查 GPU
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"\n设备: {device}")
    if device == 'cuda':
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"显存: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

    # 加载训练数据
    print(f"\n加载训练数据: {TRAIN_FILE}")
    train_data = load_triplet_data(TRAIN_FILE)
    if not train_data:
        print("❌ 训练数据为空！请先运行 02_generate.py 和 03_mine_neg.py")
        return
    print(f"训练样本数: {len(train_data)}")

    # 加载原始模型
    print(f"\n加载基础模型: {BASE_MODEL}")
    model = SentenceTransformer(str(BASE_MODEL), device=device)
    print(f"模型维度: {model.get_sentence_embedding_dimension()}")
    print(f"最大序列长度: {model.max_seq_length}")

    # 设置最大序列长度
    model.max_seq_length = MAX_SEQ_LENGTH

    # 构建训练样本（anchor + positive 格式，MultipleNegativesRankingLoss 自动用 batch 内其他样本当负例）
    print(f"\n构建训练样本...")
    train_examples = []
    for record in train_data:
        example = InputExample(texts=[
            record['anchor'],      # 查询
            record['positive'],    # 正例
        ])
        train_examples.append(example)
    print(f"训练样本数: {len(train_examples)}")

    # 创建 DataLoader
    from torch.utils.data import DataLoader
    train_dataloader = DataLoader(
        train_examples,
        shuffle=True,
        batch_size=BATCH_SIZE,
    )

    # 定义损失函数：MultipleNegativesRankingLoss（更稳定，业界标准）
    train_loss = losses.MultipleNegativesRankingLoss(model=model)

    # 计算总步数
    total_steps = len(train_dataloader) * EPOCHS
    warmup_steps = int(total_steps * WARMUP_RATIO)
    print(f"\n训练配置:")
    print(f"  Epochs: {EPOCHS}")
    print(f"  Batch Size: {BATCH_SIZE}")
    print(f"  Learning Rate: {LEARNING_RATE}")
    print(f"  总步数: {total_steps}")
    print(f"  预热步数: {warmup_steps}")
    print(f"  TripletLoss margin: {MARGIN}")

    # 开始训练
    print(f"\n{'=' * 50}")
    print("开始训练...")
    print(f"{'=' * 50}")

    start_time = datetime.now()

    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=EPOCHS,
        warmup_steps=warmup_steps,
        output_path=str(FINETUNED_MODEL),
        show_progress_bar=True,
        save_best_model=False,
    )

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print(f"\n{'=' * 50}")
    print(f"训练完成！耗时: {duration:.0f} 秒 ({duration/60:.1f} 分钟)")
    print(f"微调模型保存在: {FINETUNED_MODEL}")

    # 保存训练记录
    train_record = {
        "base_model": str(BASE_MODEL),
        "finetuned_model": str(FINETUNED_MODEL),
        "train_samples": len(train_examples),
        "epochs": EPOCHS,
        "batch_size": BATCH_SIZE,
        "learning_rate": LEARNING_RATE,
        "warmup_steps": warmup_steps,
        "margin": MARGIN,
        "max_seq_length": MAX_SEQ_LENGTH,
        "duration_seconds": duration,
        "device": device,
        "gpu": torch.cuda.get_device_name(0) if device == 'cuda' else 'N/A',
        "timestamp": datetime.now().isoformat(),
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    record_file = RESULTS_DIR / "train_record.json"
    with open(record_file, 'w', encoding='utf-8') as f:
        json.dump(train_record, f, ensure_ascii=False, indent=2)
    print(f"训练记录保存在: {record_file}")


if __name__ == "__main__":
    main()
