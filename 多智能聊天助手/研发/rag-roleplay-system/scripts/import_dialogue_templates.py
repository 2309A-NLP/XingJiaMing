#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导入对话模板到dialogue_rag知识库（追加模式）"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyPDF2 import PdfReader
from pymilvus import MilvusClient
from src.config.settings import MILVUS_CONFIG

def load_pdf_simple(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except Exception as e:
        print(f"PDF read failed: {e}")
        return ""

def create_collection_if_not_exists(client, collection_name, dimension):
    """如果集合不存在则创建，存在则跳过"""
    try:
        collections = client.list_collections()
        if collection_name in collections:
            print(f"Collection {collection_name} already exists, skipping creation")
            return False
        
        client.create_collection(
            collection_name=collection_name,
            dimension=dimension,
            primary_field_name="id",
            vector_field_name="vector",
            auto_id=True
        )
        print(f"Created new collection: {collection_name}")
        return True
    except Exception as e:
        print(f"Collection operation failed: {e}")
        return False

def insert_chunks(client, collection_name, chunks, vectors, role_name):
    try:
        data = []
        for chunk, vector in zip(chunks, vectors):
            data.append({"vector": vector, "text": chunk[:1000], "role_name": role_name})

        client.insert(collection_name=collection_name, data=data)
        print(f"Inserted {len(data)} records")
        return len(data)
    except Exception as e:
        print(f"Insert failed: {e}")
        return 0

def main():
    print("========== Importing Dialogue Templates (Append Mode) ==========")

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, "data", "PDF对话模版")

    if not os.path.exists(data_dir):
        print(f"Dir not found: {data_dir}")
        return

    client = MilvusClient(uri=f"http://{MILVUS_CONFIG['host']}:{MILVUS_CONFIG['port']}")
    collection_name = "dialogue_rag"
    total_inserted = 0

    for root, dirs, files in os.walk(data_dir):
        for file in files:
            if file.endswith('.pdf'):
                pdf_path = os.path.join(root, file)
                role_name = os.path.basename(os.path.dirname(pdf_path))
                print(f"\nProcessing: {role_name} - {file}")

                raw_text = load_pdf_simple(pdf_path)
                if not raw_text:
                    print(f"Warning: Empty PDF")
                    continue

                print(f"Text length: {len(raw_text)} chars")

                from src.rag.chunking import chunk_text
                chunks = chunk_text(raw_text)
                print(f"Chunks: {len(chunks)}")

                from src.rag.embedding import embed_texts
                vectors = embed_texts(chunks)

                if not vectors or len(vectors) == 0 or len(vectors[0]) == 0:
                    print(f"Warning: Embedding failed")
                    continue

                print(f"Vector dim: {len(vectors[0])}")

                create_collection_if_not_exists(client, collection_name, len(vectors[0]))
                inserted = insert_chunks(client, collection_name, chunks, vectors, role_name)
                total_inserted += inserted

    print(f"\n========== Done! Total inserted: {total_inserted} records ==========")

if __name__ == "__main__":
    main()