# RAGFlow 部署文档

## 1. 环境要求

### 硬件要求

| 资源 | 最低要求 | 推荐配置 |
|------|----------|----------|
| CPU | 4核 | 8核+ |
| 内存 | 8GB | 16GB+ |
| GPU | 无（CPU模式） | RTX 4060+（GPU模式） |
| 磁盘 | 50GB | 100GB+ SSD |

### 软件要求

| 软件 | 版本 |
|------|------|
| Docker | 24.0+ |
| Docker Compose | 2.20+ |
| NVIDIA Container Toolkit | 最新（GPU模式） |
| WSL2 | Windows 11（WSL部署） |
| Ollama | 0.9.2+（本地LLM） |

## 2. 部署步骤

### 2.1 下载RAGFlow

```bash
cd /path/to/project
git clone https://github.com/infiniflow/ragflow.git
cd ragflow/docker
```

### 2.2 配置环境变量

编辑 `.env` 文件：

```bash
# RAGFlow镜像
RAGFLOW_IMAGE=infiniflow/ragflow:v0.26.0

# 设备模式（cpu或gpu）
DEVICE=gpu

# 端口配置
SVR_HTTP_PORT=9380
SVR_WEB_HTTP_PORT=80
SVR_WEB_HTTPS_PORT=443
```

### 2.3 启动服务

**CPU模式**：
```bash
docker compose --profile cpu up -d
```

**GPU模式**：
```bash
docker compose --profile gpu up -d
```

### 2.4 验证部署

```bash
# 检查容器状态
docker ps | grep ragflow

# 检查API健康
curl http://localhost:9380/api/system/status

# 检查GPU（GPU模式）
docker exec docker-ragflow-gpu-1 python3 -c "import torch; print(torch.cuda.is_available())"
```

## 3. 本地LLM部署（Ollama）

### 3.1 安装Ollama

```bash
# 下载Ollama
wget -c "https://github.com/ollama/ollama/releases/download/v0.9.2/ollama-linux-amd64.tgz" -O /tmp/ollama.tgz

# 解压安装
sudo tar -xzf /tmp/ollama.tgz -C /usr/local/

# 启动服务（绑定所有接口，支持Docker访问）
OLLAMA_HOST=0.0.0.0 /usr/local/bin/ollama serve &
```

### 3.2 下载模型

```bash
# 下载qwen2.5:3b模型（约1.9GB）
ollama pull qwen2.5:3b

# 验证模型
ollama list
```

### 3.3 配置RAGFlow使用Ollama

**方式一：通过数据库配置**

```sql
-- 添加模型到tenant_llm表
INSERT INTO tenant_llm (tenant_id, llm_factory, model_type, llm_name, api_key, api_base, max_tokens, status)
VALUES ('your_tenant_id', 'OpenAI-API-Compatible', 'chat', 'qwen2.5:3b', 'ollama', 'http://host.docker.internal:11434/v1', 4096, '1');

-- 添加到tenant_model表
INSERT INTO tenant_model (model_name, provider_id, instance_id, model_type, status)
VALUES ('qwen2.5:3b', 'provider_id', 'instance_id', 'chat', 'active');
```

**方式二：通过前端页面配置**

1. 登录 http://localhost:80
2. 进入 设置 → 模型管理
3. 添加模型提供商：OpenAI-API-Compatible
   - Base URL: http://host.docker.internal:11434/v1
   - API Key: ollama
4. 添加模型实例：Ollama
5. 添加模型：qwen2.5:3b (chat类型)

### 3.4 更新对话使用本地模型

```bash
curl -X PUT "http://localhost:9380/api/v1/chats/{chat_id}" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_token" \
  -d '{
    "llm_id": "qwen2.5:3b@Ollama@OpenAI-API-Compatible"
  }'
```

## 4. 模型配置

### 4.1 配置Embedding（SiliconFlow）

1. 添加模型提供商：SILICONFLOW
   - API Key: 你的SiliconFlow API Key
2. 选择Embedding模型：BAAI/bge-m3

### 4.2 配置Rerank（SiliconFlow）

1. 选择Rerank模型：BAAI/bge-reranker-v2-m3

## 5. 知识库创建

### 5.1 创建知识库

```bash
curl -X POST 'http://localhost:9380/api/v1/datasets' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer your_token' \
  -d '{"name": "知识库名称", "chunk_method": "paper"}'
```

### 5.2 上传文档

```bash
curl -X POST 'http://localhost:9380/api/v1/datasets/{dataset_id}/documents' \
  -H 'Authorization: Bearer your_token' \
  -F 'file=@"/path/to/document.pdf"'
```

### 5.3 触发解析

```bash
curl -X POST 'http://localhost:9380/api/v1/datasets/{dataset_id}/chunks' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer your_token' \
  -d '{"document_ids": ["{document_id}"]}'
```

## 6. API使用

### 6.1 问答接口

```bash
curl -X POST 'http://localhost:9380/api/v1/chats/{chat_id}/completions' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer your_token' \
  -d '{"question": "你的问题", "stream": false}'
```

### 6.2 响应格式

```json
{
  "code": 0,
  "data": {
    "answer": "回答内容",
    "reference": [...]
  },
  "message": "success"
}
```

## 7. 常见问题

### Q: Ollama从Docker容器无法访问
A: 确保Ollama绑定到0.0.0.0（`OLLAMA_HOST=0.0.0.0`），Docker容器通过`host.docker.internal:11434`访问。

### Q: 切换GPU后PyTorch未安装
A: 在`.env`中设置`DEVICE=gpu`，重启容器会自动安装PyTorch。

### Q: 解析任务卡住
A: 重置文档状态并重新触发解析：
```python
# 通过数据库重置
UPDATE document SET run = '0' WHERE id = 'doc_id';
DELETE FROM task WHERE doc_id = 'doc_id' AND progress < 1;
```
然后通过API重新触发解析。

### Q: 内存持续增长
A: 检查是否有未完成的解析任务，清理僵尸任务。

### Q: Ollama并发性能差
A: Ollama默认parallel=2，受显存限制。降低并发数或升级显存可改善。
