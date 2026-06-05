#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymilvus import MilvusClient
from src.config.settings import DATA_DIR, MILVUS_CONFIG
from src.rag.load_pdf import load_pdf
from src.rag.chunking import chunk_text
from src.rag.embedding import embed_texts
from src.db.mysql import update_character_knowledge_base

def connect_milvus():
    try:
        client = MilvusClient(uri=f"http://{MILVUS_CONFIG['host']}:{MILVUS_CONFIG['port']}", timeout=30)
        print("Milvus connected successfully")
        return client
    except Exception as e:
        print(f"Milvus connection failed: {e}")
        sys.exit(1)

def create_collection(client, collection_name, dimension):
    try:
        if client.has_collection(collection_name):
            print(f"Collection {collection_name} exists, dropping...")
            client.drop_collection(collection_name)
        
        client.create_collection(
            collection_name=collection_name,
            dimension=dimension,
            primary_field_name="id",
            vector_field_name="vector",
            auto_id=True
        )
        
        client.create_index(
            collection_name=collection_name,
            field_name="vector",
            index_type="HNSW",
            metric_type="COSINE",
            params={"M": 8, "efConstruction": 64}
        )
        
        print(f"Collection {collection_name} created")
        return True
    except Exception as e:
        print(f"Failed to create collection: {e}")
        return False

def insert_chunks(client, collection_name, chunks, vectors):
    try:
        entities = []
        for chunk, vector in zip(chunks, vectors):
            entities.append({"vector": vector, "text": chunk})
        
        if entities:
            result = client.insert(collection_name=collection_name, data=entities)
            insert_count = len(result['ids'])
            print(f"Inserted {insert_count} records into {collection_name}")
            return insert_count
        else:
            print("No data to insert")
            return 0
    except Exception as e:
        print(f"Failed to insert data: {e}")
        return 0

def process_pdf(pdf_path, collection_name):
    print(f"\nProcessing PDF: {pdf_path}")
    raw_text = load_pdf(pdf_path)
    print(f"Text length: {len(raw_text)}")
    
    chunks = chunk_text(raw_text)
    print(f"Chunks: {len(chunks)}")
    
    if not chunks:
        return 0
    
    vectors = embed_texts(chunks)
    vec_dim = len(vectors[0])
    print(f"Vector dimension: {vec_dim}")
    
    client = connect_milvus()
    create_collection(client, collection_name, vec_dim)
    insert_count = insert_chunks(client, collection_name, chunks, vectors)
    return insert_count

def main():
    print("Starting knowledge base creation...")
    
    # Use project root path
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(project_root, "data", "PDF数据集")
    
    # Medical
    medical_pdf = os.path.join(data_dir, "医疗数据集", "医疗门诊真实病例数据集（可入知识库版）.pdf")
    if os.path.exists(medical_pdf):
        process_pdf(medical_pdf, "medical_rag")
    else:
        print(f"Medical PDF not found: {medical_pdf}")
    
    # Psychology
    psychology_pdf = os.path.join(data_dir, "心理专家数据集", "真实心理数据集（知识库专用）.pdf")
    if os.path.exists(psychology_pdf):
        process_pdf(psychology_pdf, "psychology_rag")
    else:
        print(f"Psychology PDF not found: {psychology_pdf}")
    
    # Update MySQL
    print("\nUpdating MySQL character configuration...")
    try:
        update_character_knowledge_base(1, "law_rag")
        update_character_knowledge_base(2, "psychology_rag")
        update_character_knowledge_base(3, "medical_rag")
        print("Character configuration updated")
    except Exception as e:
        print(f"Failed to update character config: {e}")
    
    print("\nKnowledge base creation completed!")

if __name__ == "__main__":
    main()
