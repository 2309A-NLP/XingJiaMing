#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
处理医疗和心理PDF数据集，创建相应的Milvus集合
"""

import os
import sys
from pymilvus import MilvusClient, exceptions

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config.settings import MILVUS_CONFIG
from src.rag.load_pdf import load_pdf
from src.rag.chunking import chunk_text
from src.rag.embedding import embed_texts

# 获取项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "PDF数据集")
DIALOGUE_DIR = os.path.join(PROJECT_ROOT, "data", "PDF对话模版")

print(f"项目根目录: {PROJECT_ROOT}")
print(f"数据目录: {DATA_DIR}")
print(f"对话模板目录: {DIALOGUE_DIR}")

# 连接Milvus
def connect_milvus():
    """连接Milvus"""
    try:
        client = MilvusClient(
            uri=f"http://{MILVUS_CONFIG['host']}:{MILVUS_CONFIG['port']}",
            timeout=30
        )
        print("✅ Milvus连接成功")
        return client
    except Exception as e:
        print(f"❌ Milvus连接失败: {e}")
        return None

# 创建Milvus集合
def create_collection(client, collection_name, dimension):
    """创建Milvus集合"""
    if not client:
        return False
    
    try:
        # 检查集合是否存在
        if client.has_collection(collection_name):
            print(f"⚠️  集合 {collection_name} 已存在，将删除并重新创建")
            client.drop_collection(collection_name)
        
        # 创建集合
        client.create_collection(
            collection_name=collection_name,
            dimension=dimension,
            primary_field_name="id",
            vector_field_name="vector",
            auto_id=True
        )
        
        # 创建索引
        client.create_index(
            collection_name=collection_name,
            field_name="vector",
            index_type="HNSW",
            metric_type="COSINE",
            params={"M": 8, "efConstruction": 64}
        )
        
        print(f"✅ 集合 {collection_name} 创建成功")
        return True
    except Exception as e:
        print(f"❌ 创建集合失败: {e}")
        return False

# 插入数据到Milvus
def insert_chunks(client, collection_name, chunks, vectors):
    """插入数据到Milvus"""
    if not client:
        return 0
    
    try:
        entities = []
        for chunk, vector in zip(chunks, vectors):
            entities.append({
                "vector": vector,
                "text": chunk
            })
        
        # 批量插入
        if entities:
            result = client.insert(
                collection_name=collection_name,
                data=entities
            )
            insert_count = len(result['ids'])
            print(f"✅ 成功插入 {insert_count} 条数据到 {collection_name}")
            return insert_count
        else:
            print("⚠️  没有数据可插入")
            return 0
    except Exception as e:
        print(f"❌ 插入数据失败: {e}")
        return 0

# 处理PDF文件并创建Milvus集合
def process_pdf_and_create_collection(pdf_path, collection_name):
    """处理PDF文件并创建Milvus集合"""
    try:
        # 1. 读取PDF
        print(f"\n📄 正在读取PDF: {pdf_path}")
        raw_text = load_pdf(pdf_path)
        print(f"✅ 读取完成，文本长度: {len(raw_text)}")
        
        # 2. 切分文本
        print("🔪 正在切分文本...")
        chunks = chunk_text(raw_text)
        print(f"✅ 切分完成，共 {len(chunks)} 个片段")
        
        if not chunks:
            print("⚠️  没有切分出文本片段")
            return 0
        
        # 3. 向量化
        print("🧠 正在向量化...")
        vectors = embed_texts(chunks)
        if not vectors:
            print("⚠️  向量化失败")
            return 0
        
        vec_dim = len(vectors[0])
        print(f"✅ 向量化完成，向量维度: {vec_dim}")
        
        # 4. 连接Milvus
        client = connect_milvus()
        if not client:
            return 0
        
        # 5. 创建集合
        if not create_collection(client, collection_name, vec_dim):
            return 0
        
        # 6. 插入数据
        insert_count = insert_chunks(client, collection_name, chunks, vectors)
        return insert_count
    except Exception as e:
        print(f"❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()
        return 0

# 主函数
def main():
    print("🚀 开始处理医疗和心理PDF数据集...")
    
    # 处理医疗数据集
    medical_pdf = os.path.join(DATA_DIR, "医疗数据集", "医疗门诊真实病例数据集（可入知识库版）.pdf")
    if os.path.exists(medical_pdf):
        medical_count = process_pdf_and_create_collection(medical_pdf, "medical_rag")
        print(f"\n🏥 医疗数据集处理完成，插入 {medical_count} 条数据")
    else:
        print(f"❌ 医疗PDF文件不存在: {medical_pdf}")
    
    # 处理心理数据集
    psychology_pdf = os.path.join(DATA_DIR, "心理专家数据集", "真实心理数据集（知识库专用）.pdf")
    if os.path.exists(psychology_pdf):
        psychology_count = process_pdf_and_create_collection(psychology_pdf, "psychology_rag")
        print(f"\n🧠 心理数据集处理完成，插入 {psychology_count} 条数据")
    else:
        print(f"❌ 心理PDF文件不存在: {psychology_pdf}")
    
    # 处理对话模板
    if os.path.exists(DIALOGUE_DIR):
        dialogue_pdfs = []
        # 收集所有对话模板PDF
        for root, dirs, files in os.walk(DIALOGUE_DIR):
            for file in files:
                if file.endswith('.pdf'):
                    dialogue_pdfs.append(os.path.join(root, file))
        
        if dialogue_pdfs:
            print(f"\n💬 发现 {len(dialogue_pdfs)} 个对话模板PDF")
            all_dialogue_chunks = []
            
            # 处理所有对话模板
            for pdf_path in dialogue_pdfs:
                print(f"\n📄 正在读取对话模板: {pdf_path}")
                try:
                    raw_text = load_pdf(pdf_path)
                    chunks = chunk_text(raw_text)
                    all_dialogue_chunks.extend(chunks)
                    print(f"✅ 读取完成，获取 {len(chunks)} 个对话片段")
                except Exception as e:
                    print(f"❌ 读取失败: {e}")
            
            if all_dialogue_chunks:
                print(f"\n🔪 共收集 {len(all_dialogue_chunks)} 个对话片段")
                
                # 向量化
                print("🧠 正在向量化对话模板...")
                vectors = embed_texts(all_dialogue_chunks)
                if vectors:
                    vec_dim = len(vectors[0])
                    print(f"✅ 向量化完成，向量维度: {vec_dim}")
                    
                    # 连接Milvus
                    client = connect_milvus()
                    if client:
                        # 创建对话模板集合
                        if create_collection(client, "dialogue_rag", vec_dim):
                            insert_count = insert_chunks(client, "dialogue_rag", all_dialogue_chunks, vectors)
                            print(f"💬 对话模板处理完成，插入 {insert_count} 条数据")
        else:
            print(f"⚠️  没有找到对话模板PDF文件")
    else:
        print(f"❌ 对话模板目录不存在: {DIALOGUE_DIR}")
    
    print("\n🎉 所有数据集处理完成！")

if __name__ == "__main__":
    main()
