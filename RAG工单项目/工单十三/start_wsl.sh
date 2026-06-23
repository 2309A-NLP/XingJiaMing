#!/bin/bash
# 工单十二 WSL 启动脚本（start.bat 调用）

cd "/mnt/e/桌面/项目文件/RAG工单项目/工单十二"

# 1. 启动 Docker
echo "[1/2] Starting Docker containers..."
sudo service docker start 2>/dev/null
docker start etcd minio redis milvus neo4j 2>/dev/null
sleep 5

# 2. 启动后端
echo "[2/2] Starting backend on port 8012..."
NO_PROXY='*' no_proxy='*' PYTHONUNBUFFERED=1 PYTHONUTF8=1 \
  MILVUS_HOST=127.0.0.1 REDIS_HOST=127.0.0.1 NEO4J_URI=bolt://127.0.0.1:7687 \
  /home/swcqybz/.hermes/hermes-agent/venv/bin/python start_wsl.py
