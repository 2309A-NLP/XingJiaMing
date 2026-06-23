# 工单十一：Embedding 模型微调

## 项目目标

在金融领域数据上微调 BGE Embedding 模型，提升 RAG 系统的检索准确性。

## 技术方案

| 项目 | 方案 |
|------|------|
| 基础模型 | BAAI/bge-base-zh-v1.5（中文，768维） |
| 训练框架 | sentence-transformers 5.5.1 |
| 损失函数 | MultipleNegativesRankingLoss |
| 训练数据 | 9份金融年报，LLM自动生成问答对 |
| 负例策略 | 困难负例（检索挖掘） |
| GPU | RTX 4060 8GB |

## 评估结果

| 指标 | 微调前 | 微调后 | 提升 |
|------|--------|--------|------|
| **Recall@10** | 0.5213 | **0.5759** | **+10.5%** ✅ |
| **MRR** | 0.3023 | **0.3630** | **+20.1%** ✅ |
| **NDCG@10** | 0.3547 | **0.4145** | **+16.9%** ✅ |
| **Precision@10** | 0.0522 | **0.0577** | **+10.5%** ✅ |

**结论：微调有效，所有指标全面提升。**

## 当前不足与优化方向

### 当前效果分析

本次微调实现了所有指标正向提升（Recall@10 +10.5%，MRR +20.1%），但提升幅度属于**中等水平**，主要原因：

| 原因 | 说明 |
|------|------|
| 训练数据量少 | 仅1,220条，业界通常用10,000-100,000条 |
| 训练轮次保守 | 仅1个epoch，防坍塌但效果有限 |
| 领域差异小 | 金融年报语言相对通用，专业术语不多 |
| 测试集非人工标注 | LLM自动生成的测试query可能和训练数据分布重叠 |

### 优化方案

#### 方案一：增加训练数据（预期提升 +5-10%）

```bash
# 当前：采样400段，生成1,220条
# 优化：采样1,000段，生成3,000-5,000条
# 修改 scripts/02_generate.py 中的 SAMPLE_SIZE = 1000
```

- 增加金融文档数量（加入更多年报、研报、公告）
- 每段生成5个问题（当前3个）
- 预计LLM调用时间：5-6小时

#### 方案二：增加训练轮次（预期提升 +3-5%）

```bash
# 当前：EPOCHS = 1
# 优化：EPOCHS = 3~5
# 修改 scripts/05_train.py 中的 EPOCHS = 3
```

- 需要同时监控过拟合（观察训练loss是否下降但评估指标不再提升）
- 建议配合早停策略（early stopping）

#### 方案三：使用更专业的金融数据（预期提升 +10-20%）

当前数据来源是通用金融年报，语言偏正式。可以加入：
- 金融专业术语问答（如"什么是MLF？""LPR和贷款利率的关系？"）
- 投资者互动问答（董秘回复、投资者提问）
- 金融新闻摘要
- 行业研报核心观点

这类数据的专业术语密度更高，微调效果更明显。

#### 方案四：升级模型（预期提升 +5-10%）

| 模型 | 参数量 | 维度 | 显存需求 | 效果 |
|------|--------|------|---------|------|
| bge-base-zh-v1.5（当前） | 110M | 768 | ~2GB | 基准 |
| bge-large-zh-v1.5 | 326M | 1024 | ~4GB | +5-10% |
| bge-m3 | 568M | 1024 | ~6GB | +10-15% |

注意：换大模型需要更多显存，RTX 4060 8GB 可以跑 bge-large，但 bge-m3 比较紧张。

#### 方案五：优化数据质量（预期提升 +5-15%）

当前问题：
- LLM生成的问题可能质量参差不齐
- 部分训练样本的正例段落包含表格/列表数据（不适合语义匹配）
- 困难负例可能太难（和正例太像，导致模型学不到有效信号）

优化方法：
- 过滤掉表格/列表类型的段落（修改 `01_chunk.py` 的 `_is_table_or_list` 过滤逻辑）
- 人工审核一批训练数据，剔除低质量样本
- 调整困难负例的难度（取Top5-10而非Top1）

### 优化优先级建议

| 优先级 | 方案 | 成本 | 收益 |
|--------|------|------|------|
| ⭐⭐⭐ | 增加训练数据到5,000条 | 5-6小时LLM调用 | +5-10% |
| ⭐⭐⭐ | 优化数据质量（过滤表格段落） | 1小时改代码 | +5-15% |
| ⭐⭐ | 训练3个epoch | 2分钟 | +3-5% |
| ⭐⭐ | 加入专业金融术语数据 | 需要人工收集 | +10-20% |
| ⭐ | 换bge-large模型 | 重新下载+训练 | +5-10% |

**推荐组合：** 方案一 + 方案三 + 方案二（增加数据 + 专业数据 + 多轮训练），预计可将 Recall@10 提升到 0.65-0.70。

## 目录结构

```
工单十一/
├── data/
│   ├── raw/              # 原始金融文档（9份年报）
│   ├── chunks.jsonl      # 分段结果（16,266段）
│   ├── train.jsonl       # 训练集（1,220条）
│   ├── train_final.jsonl # 训练集+困难负例
│   └── test.jsonl        # 测试集（495条）
├── model/
│   └── bge-finetuned/    # 微调后的模型（391MB）
├── results/
│   ├── baseline.json     # 微调前评估结果
│   ├── finetuned.json    # 微调后评估结果
│   ├── comparison.json   # 对比报告
│   └── train_record.json # 训练记录
├── scripts/
│   ├── 01_chunk.py       # 文档分段
│   ├── 02_generate.py    # LLM生成问答对
│   ├── 03_mine_neg.py    # 挖掘困难负例
│   ├── 04_evaluate.py    # 评估（微调前后对比）
│   └── 05_train.py       # 微调训练
└── README.md             # 本文件
```

## 执行流程

```bash
# 激活环境
conda activate emb

# 1. 文档分段
python scripts/01_chunk.py

# 2. LLM生成问答对（约2小时，调用mimo API）
python scripts/02_generate.py

# 3. 挖掘困难负例（约3分钟，GPU）
python scripts/03_mine_neg.py

# 4. 微调训练（约30秒，GPU）
python scripts/05_train.py

# 5. 评估对比
python scripts/04_evaluate.py --both
```

## 训练参数

| 参数 | 值 | 说明 |
|------|-----|------|
| Epochs | 1 | 先1轮试效果，防过拟合 |
| Batch Size | 16 | 8GB显存安全值 |
| Learning Rate | 5e-6 | 低学习率，防模型坍塌 |
| Max Seq Length | 128 | token数 |
| Warmup Ratio | 0.1 | 前10%步数预热 |

## 踩坑记录

1. **模型坍塌**：TripletLoss + 高学习率(2e-5)导致所有向量趋同 → 换用MultipleNegativesRankingLoss + 低学习率(5e-6)解决
2. **OOM**：batch_size=16 + seq_len=256 超出8GB显存 → 降到 batch=8/seq=128
3. **conda run装错地方**：`conda run -n emb pip install` 会装到hermes venv → 用绝对路径 `/home/swcqybz/miniconda3/envs/emb/bin/pip install`
4. **PyTorch重装太慢**：2GB CUDA包下载半小时 → 用.pth文件复用hermes venv的包

## 环境依赖

- Python 3.11（conda emb环境）
- PyTorch 2.12.0+cu130
- sentence-transformers 5.5.1
- accelerate
- numpy, requests
