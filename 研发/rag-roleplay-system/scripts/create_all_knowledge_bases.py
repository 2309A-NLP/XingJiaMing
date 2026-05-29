#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""创建所有知识库集合"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.rag.load_pdf import load_pdf
from src.rag.chunking import chunk_text
from src.rag.embedding import embed_texts
from src.rag.retrieval import create_collection, insert_vectors
from src.db.mysql import update_character_knowledge_base, get_character_info

def create_knowledge_base(pdf_path, collection_name):
    """创建知识库集合"""
    print(f"正在处理 {pdf_path}...")
    
    # 读取PDF
    raw_text = load_pdf(pdf_path)
    if not raw_text:
        print(f"警告：未能读取 {pdf_path}")
        return False
    
    # 切分文本
    chunks = chunk_text(raw_text)
    print(f"文本切分完成，共 {len(chunks)} 个片段")
    
    # 向量化
    vectors = embed_texts(chunks)
    print(f"向量化完成，向量维度：{len(vectors[0]) if vectors else 0}")
    
    # 创建或更新集合
    create_collection(collection_name, dimension=len(vectors[0]) if vectors else 1024)
    print(f"集合 {collection_name} 创建成功")
    
    # 插入数据
    result = insert_vectors(vectors, chunks, collection_name)
    insert_count = result['insert_count'] if result else 0
    print(f"数据插入完成，共插入 {insert_count} 条记录")
    
    return True

def main():
    print("========== 创建所有知识库 ==========")
    
    # 数据目录
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "PDF数据集")
    
    # 创建法律知识库
    law_pdf = os.path.join(data_dir, "法律数据集", "中华人民共和国刑法_20201226.pdf")
    if os.path.exists(law_pdf):
        create_knowledge_base(law_pdf, "law_rag")
    else:
        print(f"未找到法律数据集：{law_pdf}")
    
    # 创建医疗知识库
    medical_pdf = os.path.join(data_dir, "医疗数据集", "医疗门诊真实病例数据集（可入知识库版）.pdf")
    if os.path.exists(medical_pdf):
        create_knowledge_base(medical_pdf, "medical_rag")
    else:
        print(f"未找到医疗数据集：{medical_pdf}")
    
    # 创建心理知识库
    psychology_pdf = os.path.join(data_dir, "心理专家数据集", "真实心理数据集（知识库专用）.pdf")
    if os.path.exists(psychology_pdf):
        create_knowledge_base(psychology_pdf, "psychology_rag")
    else:
        print(f"未找到心理数据集：{psychology_pdf}")
    
    # 更新MySQL中的角色配置
    print("\n========== 更新角色知识库配置 ==========")
    try:
        # 更新法律角色
        update_character_knowledge_base(1, "law_rag")
        # 更新心理角色
        update_character_knowledge_base(2, "psychology_rag")
        # 更新医疗角色
        update_character_knowledge_base(3, "medical_rag")
        print("角色配置更新成功")
    except Exception as e:
        print(f"更新角色配置时出错：{e}")
    
    print("\n========== 知识库创建完成 ==========")

if __name__ == "__main__":
    main()
