# -*- coding: utf-8 -*-  # 指定文件编码为 utf-8
"""
结果重排序模块（Rerank）

本模块负责对向量检索返回的结果进行重新排序，是 RAG 系统的检索优化组件。

为什么需要 Rerank？
- 向量检索（Milvus）是"粗排"：基于向量距离进行快速匹配，召回大量候选文档
- Rerank 是"精排"：使用专门的交叉注意力模型，精细计算每个文档与查询的相关性
- 通过粗排+精排的两阶段策略，兼顾了检索速度和准确率

主要功能：
1. 使用 BGE-Reranker 模型对检索结果进行语义级精排
2. 提高最终送入 LLM 的上下文质量

技术栈：
- PyTorch: 深度学习框架
- Hugging Face Transformers: 加载预训练序列分类模型
- BGE-Reranker: 专门的中文重排序模型

Rerank 与 Embedding 的区别：
- Embedding 模型将文本编码为固定向量（双向编码器 Bi-Encoder）
- Rerank 模型直接计算 query-doc 对的相关性分数（交叉编码器 Cross-Encoder）
- Cross-Encoder 精度更高但速度更慢，所以只用于重排少量候选（top_k=10 → rerank_top_k=3）
"""

import torch                             # PyTorch 深度学习框架
from ..config.settings import MODEL_PATH # 模型路径配置（从 settings 读取）

# 全局变量（延迟加载，避免模块导入时崩溃）
_tokenizer = None  # Rerank 模型的分词器
_model = None      # Rerank 模型实例（AutoModelForSequenceClassification）


def _lazy_load():
    """延迟加载重排序模型

    在首次调用 rerank() 时才会真正加载模型到内存。
    这样做的好处：
    1. 如果系统不使用 Rerank（如纯 LLM 对话），则不需要加载模型
    2. 应用启动时更快，不需要加载所有模型
    3. 按需加载，节省内存资源
    """
    global _tokenizer, _model
    if _model is None:  # 只加载一次
        # 从 Hugging Face 的 AutoModel 加载序列分类模型
        # BGE-Reranker 本质上是一个二分类模型，输出两个类别的分数
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        rerank_model_path = MODEL_PATH["rerank"]  # 从配置获取模型路径
        # 加载预训练的分词器（与 BERT/RoBERTa 架构兼容）
        _tokenizer = AutoTokenizer.from_pretrained(rerank_model_path)
        # 加载预训练的序列分类模型
        _model = AutoModelForSequenceClassification.from_pretrained(rerank_model_path)
        _model.eval()  # 设置为评估模式（禁用 Dropout 等训练专用层）


def rerank(query, docs):
    """
    对检索结果进行重排序

    使用 Cross-Encoder 架构的 Reranker 模型，计算每个文档与查询的语义相关性分数。
    相比向量检索的 Bi-Encoder 架构，Cross-Encoder 能捕捉 query 和 doc 之间的细粒度交互。

    处理流程：
    1. 将 query 与每个 doc 拼接成文本对
    2. Tokenizer 编码为模型输入
    3. 模型推理，输出相关性分数
    4. 按分数从高到低排序

    Args:
        query: 用户查询（原始问题文本）
        docs: 向量检索返回的文档列表（待重排的候选文本）

    Returns:
        list: 按相关性从高到低排序后的文档列表
              返回结果中的文档数量取决于输入 docs 的长度
    """
    if not docs:  # 空列表直接返回
        return []

    _lazy_load()  # 确保模型已加载

    # 编码 query-doc 对
    # Cross-Encoder 的输入格式是 [(query, doc1), (query, doc2), ...]
    # 即对每个 (query, doc) 对独立编码和推理
    inputs = _tokenizer(
        [query] * len(docs),   # 将 query 复制 N 份，与每个 doc 配对
        docs,                   # 文档列表
        padding=True,           # 填充到 batch 内最大长度
        truncation=True,        # 超长文本截断（Reranker 有最大 token 限制）
        return_tensors="pt",    # 返回 PyTorch 张量
        max_length=512          # 最大 token 数（BERT 类模型的典型限制）
    )

    # 模型推理（禁用梯度计算）
    with torch.no_grad():
        # 模型输出 logits（未归一化的分数），取最后一个维度（二分类的 [相关, 不相关] 分数）
        scores = _model(**inputs).logits.squeeze(-1)

    # 将文档和分数配对，按分数降序排序
    # zip(docs, scores) 创建 (文档, 分数) 对
    # sorted(..., key=lambda x: x[1], reverse=True) 按分数从高到低排序
    ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)

    # 只返回排序后的文档列表（丢弃分数）
    return [d for d, s in ranked]
