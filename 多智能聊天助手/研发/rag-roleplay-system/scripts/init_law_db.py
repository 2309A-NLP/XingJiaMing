# -*- coding: utf-8 -*-
# init_law_db.py（和main.py同级，只运行一次）
from src.config.settings import DATA_DIR
from src.rag.load_pdf import load_pdf
from src.rag.chunking import chunk_text
from src.rag.embedding import embed_texts
from src.rag.retrieval import create_law_collection, insert_chunks
import os

if __name__ == "__main__":
    # 1. 读取你data/PDF数据集里的刑法PDF
    pdf_path = os.path.join(DATA_DIR, "中华人民共和国刑法_20201226.pdf")
    print(f"正在读取PDF：{pdf_path}")
    raw_text = load_pdf(pdf_path)

    # 2. 按法条切分
    print("正在切分文本...")
    law_chunks = chunk_text(raw_text)
    print(f"切分完成，共 {len(law_chunks)} 条法条")

    # 3. BGE-M3向量化
    print("正在BGE-M3向量化...")
    law_vectors = embed_texts(law_chunks)
    vec_dim = len(law_vectors[0]) if len(law_vectors) > 0 else 768
    print(f"向量维度：{vec_dim}")

    # 4. 创建Milvus集合+插入数据（传入实际维度）
    print("正在Milvus创建集合并插入数据...")
    create_law_collection(dimension=vec_dim)  # 适配BGE-M3的真实维度
    insert_count = insert_chunks(law_chunks, law_vectors)
    print(f"✅ 成功插入 {insert_count} 条法条到Milvus，入库完成！")