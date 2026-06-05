# -*- coding: utf-8 -*-  # 指定文件编码为 utf-8
"""
文本分块模块（Chunking）

本模块负责将长文本分割成较小的文本块，是 RAG 系统的知识库预处理组件。

为什么需要分块？
1. 模型输入限制：BGE-M3 和 Reranker 都有最大 token 限制（通常 512 tokens）
2. 检索精度：细粒度的文本块比整篇文档更容易匹配到具体问题
3. 相关性：用户的某个问题通常只涉及文档的某一段落，而不是整篇文档
4. 效率：小文本块的处理和存储更高效

主要功能：
1. 文本清洗：去除多余空白字符
2. 文本分块：按固定长度将长文本切割成小块

技术栈：
- re: Python 正则表达式模块，用于文本清洗

配置说明：
- 默认分块大小: 500 字符（在 settings.py 的 RAG_CONFIG 中配置）
- 分块策略: 固定长度分割（简单的滑动窗口策略）
- 更高级的策略（如按段落、按句子分割）未使用，但可以通过替换 chunk_text 实现
"""

import re  # 正则表达式模块


def clean_text(text: str) -> str:
    """
    清洗文本，去除多余的空白字符

    原始 PDF/文档中可能包含各种格式控制字符。
    清洗的作用是将连续的空白字符（空格、换行、制表符等）统一替换为单个空格，
    并去除首尾空白。

    Args:
        text: 原始文本（可能包含换行符、多余空格）

    Returns:
        str: 清洗后的文本（连续空白被压缩为单个空格）
    """
    # re.sub(r"\s+", " ", text): 将所有连续空白字符（\s+）替换为单个空格
    # .strip(): 去除首尾空格
    return re.sub(r"\s+", " ", text).strip()


def chunk_text(text: str, max_len=500) -> list:
    """
    将长文本分割成固定长度的文本块

    采用简单的滑动窗口策略（Fixed-size Chunking）：
    1. 从文本起始位置开始，每次取 max_len 长度的片段
    2. 不重叠（Overlap 由 RAG_CONFIG 中的 chunk_overlap 控制，本函数未实现）
    3. 按字符数切割（非 token 数），因为字符数容易计算且可控

    注意：此处的 max_len 默认 500，RAG_CONFIG 中的 chunk_size 是 512，
    两者关系是可以独立调整的，实际生效的是调用时传入的参数。

    Args:
        text: 原始文本（长文档）
        max_len: 每个文本块的最大长度（字符数），默认 500

    Returns:
        list: 文本块列表，每个元素是一个文本片段
    """
    # 先清洗文本，确保分块时不会因为多余空白浪费空间
    text = clean_text(text)

    chunks = []  # 存储所有文本块
    start = 0    # 当前块的起始位置
    total = len(text)  # 文本总长度

    # 循环分割：每次移动 max_len 个字符
    while start < total:
        # 计算块结束位置（不能超过文本长度）
        end = min(start + max_len, total)

        # 提取文本块并去除首尾空格
        chunk = text[start:end].strip()

        # 只添加非空块
        if chunk:
            chunks.append(chunk)

        # 滑动窗口向后移动 max_len 个字符
        # 注意：这里没有重叠（chunk_overlap=0）
        # 实际配置中的 chunk_overlap=50 需要另外实现
        start = end

    return chunks
