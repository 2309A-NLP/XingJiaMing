# RAG 金融问答系统 - Docker 部署文档

## 1. 环境要求

### 1.1 硬件要求

| 资源 | 最低要求 | 推荐配置 |
|------|----------|----------|
| CPU | 4 核 | 8 核 |
| 内存 | 8GB | 16GB |
| 磁盘 | 50GB | 100GB |
| GPU | NVIDIA GPU (CUDA 12.1) | NVIDIA RTX 3060+ |

### 1.2 软件要求

| 软件 | 版本 |
|------|------|
| Docker | 20.10+ |
| Docker Compose | 2.0+ |
| NVIDIA Container Toolkit | 最新版（GPU 支持） |

### 1.3 检查 GPU 支持

```bash
# 检查 NVIDIA 驱动
nvidia-smi

# 检查 Docker GPU 支持
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

## 2. 部署步骤

### 2.1 准备 AI 模型

将以下模型文件复制到服务器：

```
/models/
├── BGE-M3/              # 嵌入模型（约 2GB）
├── model-m3e-base/      # 备用嵌入模型（可选）
└── bge-reranker-base/   # 重排序模型（约 1.1GB）
```

### 2.2 创建 Docker 卷并复制模型

```bash
# 创建模型卷
docker volume create rag-ai-models

# 查看卷挂载点
docker volume inspect rag-ai-models

# 复制模型到卷（假设挂载点为 /var/lib/docker/volumes/rag-ai-models/_data）
sudo cp -r /path/to/BGE-M3 /var/lib/docker/volumes/rag-ai-models/_data/
sudo cp -r /path/to/bge-reranker-base /var/lib/docker/volumes/rag-ai-models/_data/
```

### 2.3 配置环境变量

编辑 `.env` 文件，配置以下关键参数：

```bash
# LLM API 配置
MIMO_API_KEY=your_api_key
MIMO_BASE_URL=https://api.deepseek.com/v1
MIMO_MODEL=deepseek-chat

# Vision API 配置（可选）
VISION_API_KEY=your_vision_api_key
VISION_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
VISION_MODEL=mimo-v2.5
VISION_ENABLED=true
```

### 2.4 构建并启动服务

```bash
# 进入项目目录
cd /path/to/工单十

# 构建镜像
docker-compose build

# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f backend
```

### 2.5 等待服务就绪

Backend 启动需要加载 AI 模型，约需 40-60 秒。

```bash
# 检查后端健康状态
curl http://localhost:8007/api/health

# 预期返回
{"status": "ok"}
```

## 3. 访问服务

| 服务 | 地址 |
|------|------|
| 前端页面 | http://服务器IP |
| 后端 API | http://服务器IP:8007 |
| API 文档 | http://服务器IP:8007/docs |
| Milvus | http://服务器IP:19530 |
| Redis | redis://服务器IP:6379 |

## 4. 常用命令

### 4.1 服务管理

```bash
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 重启单个服务
docker-compose restart backend

# 查看日志
docker-compose logs -f
docker-compose logs -f backend
docker-compose logs -f milvus
```

### 4.2 数据管理

```bash
# 备份数据
tar -czf backup_$(date +%Y%m%d).tar.gz data/ storage/

# 恢复数据
tar -xzf backup_20260605.tar.gz

# 清理未使用的卷
docker volume prune
```

### 4.3 容器管理

```bash
# 进入容器
docker exec -it rag-backend bash
docker exec -it rag-frontend sh

# 查看容器资源使用
docker stats

# 查看容器详细信息
docker inspect rag-backend
```

## 5. 配置说明

### 5.1 端口配置

在 `docker-compose.yml` 中修改端口映射：

```yaml
ports:
  - "80:80"      # 前端端口
  - "8007:8007"  # 后端端口
  - "19530:19530" # Milvus 端口
  - "6379:6379"   # Redis 端口
```

### 5.2 GPU 配置

如果服务器没有 GPU，需要修改 `docker-compose.yml`：

```yaml
backend:
  # 注释掉 GPU 配置
  # deploy:
  #   resources:
  #     reservations:
  #       devices:
  #         - driver: nvidia
  #           count: 1
  #           capabilities: [gpu]
```

同时修改 `Dockerfile` 使用 CPU 版本的 PyTorch：

```dockerfile
FROM python:3.10-slim

# ...
RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

### 5.3 数据持久化

以下数据通过 Docker 卷持久化：

| 卷名 | 内容 |
|------|------|
| milvus_data | Milvus 向量数据 |
| redis_data | Redis 缓存数据 |
| ai_models | AI 模型文件 |
| ./data | 文档数据（bind mount） |
| ./storage | 持久化存储（bind mount） |
| ./logs | 日志文件（bind mount） |

## 6. 故障排查

### 6.1 后端启动失败

```bash
# 查看详细日志
docker-compose logs backend

# 常见问题：
# 1. 模型路径错误 - 检查 .env 中的 EMBEDDING_MODEL_PATH
# 2. Milvus 连接失败 - 检查 milvus 服务是否启动
# 3. GPU 内存不足 - 减少模型加载数量或使用 CPU
```

### 6.2 Milvus 连接失败

```bash
# 检查 Milvus 状态
docker-compose ps milvus
docker-compose logs milvus

# 测试连接
curl http://localhost:9091/healthz
```

### 6.3 前端无法访问

```bash
# 检查 Nginx 状态
docker-compose ps frontend
docker-compose logs frontend

# 检查后端是否可访问
curl http://localhost:8007/api/health
```

### 6.4 GPU 不可用

```bash
# 检查 NVIDIA 驱动
nvidia-smi

# 检查 NVIDIA Container Toolkit
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi

# 检查 Docker 是否有 GPU 权限
docker info | grep -i runtime
```

## 7. 性能优化

### 7.1 增加 Milvus 缓存

在 `docker-compose.yml` 中为 Milvus 增加内存限制：

```yaml
milvus:
  environment:
    - CACHE_SIZE=4GB
```

### 7.2 优化后端并发

在 `run_docker.py` 中增加 worker 数量：

```python
uvicorn.run(
    "api.main:app",
    host=host,
    port=port,
    workers=4,  # 增加 worker 数量
)
```

### 7.3 使用 CDN

将前端静态文件上传到 CDN，减轻服务器负担。

## 8. 安全建议

1. **修改默认密码**：修改 `.env` 中的 API Key
2. **限制访问**：使用防火墙限制端口访问
3. **HTTPS 配置**：在 Nginx 中配置 SSL 证书
4. **日志审计**：定期检查访问日志
5. **数据备份**：定期备份 `data/` 和 `storage/` 目录
