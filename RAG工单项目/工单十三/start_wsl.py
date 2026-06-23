"""工单十二 WSL 启动脚本"""
import os, sys

# 必须在任何项目导入之前设置环境变量
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'
os.environ['MILVUS_HOST'] = '127.0.0.1'
os.environ['REDIS_HOST'] = '127.0.0.1'
os.environ['EMBEDDING_MODEL_PATH'] = '/mnt/e/AI_models/BGE-M3'
os.environ['EMBEDDING_MODELS'] = 'bge-m3:/mnt/e/AI_models/BGE-M3,m3e:/mnt/e/AI_models/model-m3e-base'
os.environ['RERANK_MODEL_PATH'] = '/mnt/e/AI_models/bge-reranker-base'
os.environ['NEO4J_URI'] = 'bolt://127.0.0.1:7687'
os.environ['NEO4J_USERNAME'] = 'neo4j'
os.environ['NEO4J_PASSWORD'] = 'neo4j123'
# os.environ['CUDA_VISIBLE_DEVICES'] = ''  # 已取消强制CPU，使用GPU

print(f"MILVUS_HOST={os.environ['MILVUS_HOST']}")
print(f"EMBEDDING_MODEL_PATH={os.environ['EMBEDDING_MODEL_PATH']}")

import uvicorn
print("Starting uvicorn on 0.0.0.0:8012 ...")
uvicorn.run("api.main:app", host="0.0.0.0", port=8012)
