# tests/test_chunking.py
# -*- coding: utf-8 -*-
import sys
import os

# 把项目根目录加入Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rag.chunking import chunk_text
from rag.load_pdf import load_pdf
from utils.logger import logger


def test_chunking():
    logger.info("开始测试 chunking...")

    # 1️⃣ 读取PDF
    text = load_pdf(r"E:\桌面\文件夹\人工智能\NLP自然语言处理\专高六\项目(RAG的角色扮演系统)\data\PDF数据集\中华人民共和国刑法_20201226.pdf")

    logger.info(f"原始文本长度: {len(text)}")

    # 2️⃣ 分块
    chunks = chunk_text(text)

    logger.info(f"分块数量: {len(chunks)}")

    # 3️⃣ 打印前3条
    print("\n========== 前3条法条 ==========")
    for i, chunk in enumerate(chunks[:3]):
        print(f"\n--- 第{i+1}条 ---")
        print(chunk)

    logger.info("chunking测试完成")


if __name__ == "__main__":
    test_chunking()