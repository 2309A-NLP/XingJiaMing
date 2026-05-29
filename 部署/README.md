# RAG 多角色对话系统 - 阿里云部署指南

## 📋 目录

- [环境要求](#环境要求)
- [快速部署](#快速部署)
- [分步部署](#分步部署)
- [配置说明](#配置说明)
- [常用命令](#常用命令)
- [故障排查](#故障排查)
- [安全建议](#安全建议)

---

## 环境要求

| 组件 | 版本/规格 | 说明 |
|------|----------|------|
| 操作系统 | Ubuntu 22.04 LTS | 阿里云 ECS |
| CPU/内存 | 4核8GB 起步 | 建议 8核16GB |
| 磁盘 | 100GB SSD | 模型文件约 4GB |
| Python | 3.10 | FastAPI + Uvicorn |
| MySQL | 8.0 | 主数据库 |
| Redis | 6.x+ | 缓存/会话 |
| Milvus | 2.4.5 | 向量数据库 (Docker) |
| Nginx | 最新 | 反向代理 |
| Docker | 最新 | 容器运行时 |

### 阿里云安全组端口

| 端口 | 协议 | 用途 |
|------|------|------|
| 22 | TCP | SSH |
| 80 | TCP | HTTP |
| 443 | TCP | HTTPS |
| 19530 | TCP | Milvus (可选, 仅内部) |

---

## 快速部署

```bash
# 1. 上传脚本到服务器
scp -r ./多角色智能问答系统部署脚本/ root@120.26.32.90:/root/deploy/

# 2. SSH 登录服务器
ssh root@120.26.32.90

# 3. 一键部署 (无域名)
sudo bash /root/deploy/deploy_all.sh

# 3. 一键部署 (有域名 + SSL)
sudo bash /root/deploy/deploy_all.sh --domain rag-chat.example.com --email admin@example.com
```

---

## 分步部署

如需分步执行或排查问题, 可按顺序单独运行每个脚本:

```bash
# Step 1: 服务器初始化 (系统更新, 安装依赖)
sudo bash 01_server_init.sh

# Step 2: Docker + Milvus 部署
sudo bash 02_docker_setup.sh

# Step 3: 应用部署 (代码, 依赖, 模型, systemd)
sudo bash 03_app_deploy.sh

# Step 4: Nginx 反向代理
sudo bash 04_nginx_setup.sh

# Step 5: SSL 证书 (需域名)
sudo bash 05_ssl_setup.sh your.domain.com admin@email.com

# Step 6: 自动备份
sudo bash 06_backup_setup.sh

# Step 7: 监控
sudo bash 07_monitoring.sh
```

---

## 配置说明

### 环境变量 (.env)

部署后配置文件位于 `/opt/rag-chat/.env`, 必须修改:

```bash
# 必须修改
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx  # DeepSeek API 密钥
MYSQL_PASSWORD=your-secure-password    # MySQL root 密码

# 可选修改
JWT_SECRET=auto-generated              # 自动生成, 无需修改
```

### 项目目录结构

```
/opt/rag-chat/
├── .env                    # 环境变量配置
├── docker-compose.yml      # Milvus Docker 配置
├── main.py                 # FastAPI 入口
├── requirements.txt        # Python 依赖
├── venv/                   # Python 虚拟环境
├── models/BAAI/
│   ├── bge-m3/             # BGE-M3 嵌入模型 (~2.2GB)
│   └── bge-reranker-base/  # BGE 重排模型 (~1.1GB)
├── static/                 # 静态文件
├── nginx/                  # Nginx 配置备份
├── logs/                   # 日志目录
│   ├── app.log             # 应用日志
│   ├── app_error.log       # 错误日志
│   ├── health_check.log    # 健康检查日志
│   └── alert.log           # 告警日志
├── backups/                # 备份目录
│   ├── mysql/              # MySQL 备份
│   ├── milvus/             # Milvus 备份
│   └── app/                # 配置备份
└── scripts/                # 运维脚本
    ├── backup_mysql.sh     # MySQL 备份
    ├── backup_milvus.sh    # Milvus 备份
    ├── backup_all.sh       # 全量备份
    ├── health_check.sh     # 健康检查
    ├── disk_alert.sh       # 磁盘告警
    └── status.sh           # 状态查看
```

---

## 常用命令

### 服务管理

```bash
# 应用服务
systemctl start rag-chat       # 启动
systemctl stop rag-chat        # 停止
systemctl restart rag-chat     # 重启
systemctl status rag-chat      # 状态
journalctl -u rag-chat -f      # 实时日志

# Nginx
systemctl reload nginx         # 重载配置
nginx -t                       # 测试配置

# Docker (Milvus)
cd /opt/rag-chat
docker compose up -d           # 启动
docker compose down            # 停止
docker compose logs -f         # 日志
docker compose ps              # 状态
```

### 运维操作

```bash
# 查看系统状态
bash /opt/rag-chat/scripts/status.sh

# 手动健康检查
bash /opt/rag-chat/scripts/health_check.sh

# 手动备份
bash /opt/rag-chat/scripts/backup_all.sh

# 查看日志
tail -f /opt/rag-chat/logs/app.log

# 回滚操作
sudo bash rollback.sh
```

---

## 故障排查

### 1. 应用无法启动

```bash
# 检查日志
journalctl -u rag-chat -n 50 --no-pager
cat /opt/rag-chat/logs/app_error.log

# 常见原因:
# - .env 配置错误
# - 端口被占用: lsof -i :8000
# - 依赖缺失: source venv/bin/activate && pip install -r requirements.txt
```

### 2. Milvus 连接失败

```bash
# 检查容器状态
docker ps -a | grep milvus
docker compose -f /opt/rag-chat/docker-compose.yml logs milvus-standalone

# 常见原因:
# - 容器未启动: docker compose up -d
# - 端口冲突: lsof -i :19530
# - 磁盘满: df -h
```

### 3. MySQL 连接失败

```bash
# 检查 MySQL 状态
systemctl status mysql
mysqladmin ping

# 重置密码
sudo mysql
ALTER USER 'root'@'localhost' IDENTIFIED BY 'new_password';
FLUSH PRIVILEGES;
```

### 4. Redis 连接失败

```bash
systemctl status redis-server
redis-cli ping  # 应返回 PONG
```

### 5. Nginx 502 Bad Gateway

```bash
# 检查 FastAPI 是否运行
curl http://localhost:8000/api/health

# 检查 Nginx 日志
tail -50 /var/log/nginx/rag-chat-error.log
```

### 6. 磁盘空间不足

```bash
# 查看磁盘使用
df -h

# 清理 Docker
docker system prune -a

# 清理旧日志
find /opt/rag-chat/logs -name "*.log.*" -mtime +7 -delete

# 清理旧备份
find /opt/rag-chat/backups -mtime +7 -delete
```

### 7. 模型下载失败

```bash
# 设置 HuggingFace 镜像 (国内加速)
export HF_ENDPOINT=https://hf-mirror.com

# 重新下载
cd /opt/rag-chat
source venv/bin/activate
python -c "
from huggingface_hub import snapshot_download
snapshot_download('BAAI/bge-m3', local_dir='models/BAAI/bge-m3', resume_download=True)
"
```

---

## 安全建议

1. **修改默认密码**: MySQL root 密码、Redis 密码
2. **启用 SSL**: 运行 `05_ssl_setup.sh` 配置 HTTPS
3. **限制 SSH**: 禁用密码登录, 仅允许密钥认证
4. **防火墙**: 仅开放必要端口 (22, 80, 443)
5. **定期更新**: `apt-get update && apt-get upgrade`
6. **备份验证**: 定期测试备份恢复流程
7. **日志审计**: 定期检查 access.log 和 alert.log

---

## 脚本清单

| 脚本 | 功能 |
|------|------|
| `01_server_init.sh` | 服务器初始化 (系统更新, 安装依赖) |
| `02_docker_setup.sh` | Docker 安装 + Milvus 启动 |
| `03_app_deploy.sh` | 应用部署 (代码, 依赖, 模型, 服务) |
| `04_nginx_setup.sh` | Nginx 反向代理配置 |
| `05_ssl_setup.sh` | SSL 证书 (Let's Encrypt) |
| `06_backup_setup.sh` | 自动备份配置 |
| `07_monitoring.sh` | 监控和告警 |
| `deploy_all.sh` | 一键部署 (调用以上所有) |
| `rollback.sh` | 回滚工具 (交互式) |
