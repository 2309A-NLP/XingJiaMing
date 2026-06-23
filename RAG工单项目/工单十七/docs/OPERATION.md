# RAGFlow 运维文档

## 1. 日常监控

### 1.1 容器状态检查

```bash
# 检查所有容器状态
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# 检查资源使用
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

### 1.2 GPU监控（GPU模式）

```bash
# GPU使用情况
nvidia-smi

# GPU实时监控
watch -n 1 nvidia-smi
```

### 1.3 服务健康检查

```bash
# API健康检查
curl -s http://localhost:9380/api/system/status | python3 -m json.tool

# Elasticsearch健康
curl -s http://localhost:9200/_cluster/health | python3 -m json.tool

# Redis连接
docker exec docker-redis-1 redis-cli ping
```

## 2. 日志管理

### 2.1 查看日志

```bash
# RAGFlow API日志
docker logs docker-ragflow-gpu-1 --tail 100

# 实时跟踪日志
docker logs -f docker-ragflow-gpu-1

# 过滤错误日志
docker logs docker-ragflow-gpu-1 2>&1 | grep -i "error\|ERROR"
```

### 2.2 日志文件位置

```bash
# 容器内日志目录
/ragflow/logs/

# 宿主机日志目录（挂载）
/path/to/ragflow/docker/ragflow-logs/
```

## 3. 数据库维护

### 3.1 MySQL操作

```bash
# 进入MySQL
docker exec -it docker-mysql-1 mysql -u root -p'infini_rag_flow' rag_flow

# 常用查询
# 查看知识库
SELECT id, name FROM knowledgebase;

# 查看文档状态
SELECT id, name, run, progress FROM document;

# 查看任务状态
SELECT id, doc_id, progress, retry_count FROM task WHERE progress < 1;

# 查看用户
SELECT id, nickname, email FROM user;
```

### 3.2 Elasticsearch操作

```bash
# 查看索引
curl -s http://localhost:9200/_cat/indices?v

# 查看集群健康
curl -s http://localhost:9200/_cluster/health?pretty

# 查看节点状态
curl -s http://localhost:9200/_cat/nodes?v
```

### 3.3 Redis操作

```bash
# 进入Redis
docker exec -it docker-redis-1 redis-cli

# 查看Redis信息
INFO stats
INFO memory
INFO clients
```

## 4. 故障排查

### 4.1 API响应慢

**可能原因**：
1. LLM API延迟高
2. Elasticsearch查询慢
3. 内存不足

**排查步骤**：
```bash
# 1. 检查资源使用
docker stats --no-stream

# 2. 检查LLM API状态
curl -s http://localhost:9380/api/v1/chats/{chat_id}/completions \
  -H 'Authorization: Bearer TOKEN' \
  -d '{"question": "测试", "stream": false}'

# 3. 检查ES性能
curl -s http://localhost:9200/_nodes/stats/indices/search?pretty
```

### 4.2 文档解析失败

**可能原因**：
1. PDF格式不支持
2. 内存不足
3. 任务卡住

**解决方案**：
```bash
# 查看任务状态
docker exec docker-mysql-1 mysql -u root -p'infini_rag_flow' rag_flow \
  -e "SELECT id, progress, retry_count FROM task WHERE doc_id = 'DOC_ID' AND progress < 1;"

# 重置卡住的任务
docker exec docker-mysql-1 mysql -u root -p'infini_rag_flow' rag_flow \
  -e "DELETE FROM task WHERE doc_id = 'DOC_ID' AND progress < 1;"

# 重置文档状态
docker exec docker-mysql-1 mysql -u root -p'infini_rag_flow' rag_flow \
  -e "UPDATE document SET run = '0' WHERE id = 'DOC_ID';"

# 重新触发解析
curl -X POST 'http://localhost:9380/api/v1/datasets/{dataset_id}/chunks' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer TOKEN' \
  -d '{"document_ids": ["DOC_ID"]}'
```

### 4.3 容器崩溃重启

**可能原因**：
1. OOM（内存溢出）
2. GPU内存不足
3. 磁盘空间不足

**排查步骤**：
```bash
# 检查容器退出原因
docker inspect docker-ragflow-gpu-1 --format '{{.State.ExitCode}}'
docker inspect docker-ragflow-gpu-1 --format '{{.State.Error}}'

# 检查系统日志
dmesg | grep -i "oom\|killed"

# 检查磁盘空间
df -h
```

## 5. 备份与恢复

### 5.1 数据备份

```bash
# 备份MySQL
docker exec docker-mysql-1 mysqldump -u root -p'infini_rag_flow' rag_flow > backup.sql

# 备份Elasticsearch
curl -X PUT "http://localhost:9200/_snapshot/backup" -H 'Content-Type: application/json' -d '{"type": "fs", "settings": {"location": "/backup"}}'

# 备份MinIO数据
docker exec docker-minio-1 mc mirror /data /backup/minio
```

### 5.2 数据恢复

```bash
# 恢复MySQL
docker exec -i docker-mysql-1 mysql -u root -p'infini_rag_flow' rag_flow < backup.sql

# 恢复Elasticsearch
curl -X POST "http://localhost:9200/_snapshot/backup/snapshot/_restore"
```

## 6. 性能优化

### 6.1 查询缓存配置

在RAGFlow前端配置：
- 启用查询缓存
- 设置缓存TTL（建议300秒）
- 设置缓存大小（建议1000条）

### 6.2 Prompt优化

减少prompt长度：
- 减少top_n（建议3-5）
- 精简system prompt
- 关闭不必要的引用格式

### 6.3 并发控制

限制并发请求数：
- 设置API限流
- 使用请求队列
- 监控内存使用

## 7. 常用命令速查

```bash
# 启动服务
docker compose --profile gpu up -d

# 停止服务
docker compose down

# 重启服务
docker compose restart

# 查看日志
docker logs -f docker-ragflow-gpu-1

# 进入容器
docker exec -it docker-ragflow-gpu-1 /bin/bash

# 检查GPU
nvidia-smi

# 检查资源
docker stats --no-stream
```
