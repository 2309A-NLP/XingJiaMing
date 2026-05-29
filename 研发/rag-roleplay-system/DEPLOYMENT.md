# RAG 角色扮演系统 — 部署文档

## 1. 项目概述

基于 RAG（Retrieval-Augmented Generation）的多角色智能对话系统，支持刑事律师、心理医生、医疗门诊三种角色，通过 Milvus 向量数据库实现知识库检索增强生成。

| 属性 | 值 |
|------|-----|
| 项目名称 | RAG 角色扮演系统 |
| 版本 | 1.0 |
| 服务地址 | http://120.26.32.90 |
| 部署环境 | Alibaba Cloud ECS (Alibaba Cloud Linux 3) |
| Python 版本 | 3.10 |

---

## 2. 系统架构

```
                 ┌──────────────────────────────┐
                 │         Nginx (port 80)       │
                 │    静态文件服务 + 反向代理     │
                 └─────────────┬────────────────┘
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  前端页面     │     │  FastAPI 后端 │────▶│  DeepSeek API │
│ (indexs.html)│     │  (port 8000) │     │  (在线大模型)  │
│  + static/   │     └──────┬───────┘     └──────────────┘
└──────────────┘            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│    MySQL      │    │    Redis      │    │   Milvus     │
│  用户/角色/   │    │  短期记忆/    │    │  向量检索/   │
│  聊天记录     │    │  验证码缓存   │    │  知识库      │
└──────────────┘    └──────────────┘    └──────────────┘
        │                                       │
        └───────────────────┬───────────────────┘
                            ▼
                   ┌──────────────┐
                   │ 本地模型推理  │
                   │ BGE-M3 (嵌入) │
                   │ BGE-Reranker │
                   └──────────────┘
```

**前后端分离架构：** Nginx 在 80 端口直接返回前端静态文件（HTML/CSS/JS），`/api/*` 请求代理转发到后端 FastAPI（8000 端口）。前后端物理分离，互不依赖。

### 核心流程

```
用户提问 → 文本嵌入(BGE-M3) → Milvus向量检索(top5)
    → 重排序(BGE-Reranker) → 取top3拼接Prompt
    → DeepSeek大模型生成回复 → 保存Redis/MySQL → 返回用户
```

---

## 3. 服务器环境

| 项目 | 信息 |
|------|------|
| OS | Alibaba Cloud Linux 3 (5.10 kernel) |
| CPU | 通用型 ECS（无 GPU） |
| 内存 | 7.3 GB |
| 磁盘 | 40 GB（已用 80%） |
| Python | 3.10 |
| 虚拟环境 | `/root/rag-project/venv` |
| 项目路径 | `/root/rag-project` |

---

## 4. 依赖组件

### 4.1 Docker 容器服务

通过 `docker-compose.yml` 管理：

| 服务 | 镜像 | 端口 | 用途 |
|------|------|------|------|
| Milvus Standalone | `milvusdb/milvus:v2.4.5` | 19530, 9091 | 向量数据库 |
| etcd | `quay.io/coreos/etcd:v3.5.5` | 2379 | Milvus 元数据 |
| MinIO | `minio/minio:RELEASE.2023-03-20` | 9000 | Milvus 对象存储 |

启动方式：
```bash
cd /root/rag-project
docker-compose up -d
```

### 4.2 Nginx

| 项目 | 值 |
|------|-----|
| 版本 | 1.20.1 |
| 监听端口 | 80 |
| 用途 | 前后端分离：直接返回静态文件, `/api/*` 反向代理到 FastAPI |

配置文件：`/etc/nginx/conf.d/rag-roleplay.conf`（项目内备份：`nginx/rag-roleplay.conf`）

### 4.3 MySQL

| 项目 | 值 |
|------|-----|
| 地址 | localhost:3306 |
| 数据库 | `rag_character_chat` |
| 字符集 | utf8mb4 |

数据表：

| 表名 | 用途 | 主要字段 |
|------|------|----------|
| `users` | 用户账号 | id, phone, name, password(SHA256), role |
| `characters` | AI 角色 | id, name, role_type, description, prompt_template, knowledge_base |
| `chat_history` | 聊天记录 | id, user_id, character_id, role, content, created_at |

### 4.4 Redis

| 项目 | 值 |
|------|-----|
| 地址 | localhost:6379 |
| 用途 | 短期对话记忆、短信验证码缓存 |
| TTL | 对话记录 300 秒，验证码 300 秒 |

Redis Key 设计：
- `chat:{user_id}:{character_id}` — 对话历史列表
- `sms_code:{phone}` — 短信验证码

### 4.5 本地 AI 模型

| 模型 | 路径 | 维度 | 用途 |
|------|------|------|------|
| BGE-M3 | `/root/rag-project/models/BAAI/bge-m3` | 1024 | 文本向量嵌入 |
| BGE-Reranker | `/root/rag-project/models/BAAI/bge-reranker-base` | — | 检索结果重排序 |

### 4.6 在线大模型 API

| 项目 | 值 |
|------|------|
| 提供商 | DeepSeek |
| API 地址 | `https://api.deepseek.com/v1` |
| 模型 | `deepseek-v4-flash` |

---

## 5. Python 依赖

完整列表见 `requirements.txt`，核心依赖版本：

| 包名 | 版本 | 用途 |
|------|------|------|
| fastapi | 0.110.0 | Web 框架 |
| uvicorn | 0.29.0 | ASGI 服务器 |
| pymilvus | 2.4.4 | Milvus 客户端 |
| redis | 5.0.3 | Redis 客户端 |
| pymysql | 1.4.6 | MySQL 驱动 |
| transformers | 4.40.0 | 模型加载推理 |
| torch | 2.11.0 | 深度学习框架 |
| sentence-transformers | 2.6.1 | 句子嵌入 |
| openai | (最新) | LLM API 调用 |
| python-dotenv | 1.0.1 | 环境变量管理 |

---

## 6. 配置文件说明

### 6.1 环境变量 (`.env`)

```ini
# 大模型 API
API_KEY=sk-xxxxxxxx           # DeepSeek API 密钥
API_URL=https://api.deepseek.com/v1

# Milvus 向量数据库
MILVUS_HOST=localhost
MILVUS_PORT=19530

# Redis 缓存
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# MySQL 数据库
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=xxx
MYSQL_DATABASE=rag_character_chat

# 本地模型路径
EMBEDDING_MODEL_PATH=/root/rag-project/models/BAAI/bge-m3
RERANK_MODEL_PATH=/root/rag-project/models/BAAI/bge-reranker-base
```

### 6.2 应用配置（`src/config/settings.py`）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| LLM_CONFIG.temperature | 0.7 | 生成随机性 |
| LLM_CONFIG.max_tokens | 1024 | 最大回复长度 |
| LLM_CONFIG.timeout | 60 | API 超时(秒) |
| RAG_CONFIG.chunk_size | 512 | 文本分块大小 |
| RAG_CONFIG.chunk_overlap | 50 | 分块重叠字符数 |
| RAG_CONFIG.top_k | 10 | Milvus 初始召回数 |
| RAG_CONFIG.rerank_top_k | 3 | 重排序后保留数 |
| REDIS_CONFIG.history_limit | 5 | 保留最近对话轮数 |

### 6.3 Nginx 配置 (`/etc/nginx/conf.d/rag-roleplay.conf`)

```
server {
    listen 80;
    server_name 120.26.32.90;

    root /var/www/rag-frontend;
    index indexs.html;

    # API 请求转发给 FastAPI 后端
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # 静态文件直接由 Nginx 返回
    location /static/ {
        alias /var/www/rag-frontend/static/;
    }

    # 主页面
    location / {
        try_files $uri /indexs.html;
    }
}
```

请求流程：
- `GET /` → Nginx 直接返回 `indexs.html`
- `GET /static/*` → Nginx 直接返回静态文件
- `POST /api/*` → Nginx 代理转发到 FastAPI (127.0.0.1:8000)

---

## 7. 项目文件结构

```
/root/rag-project/
├── src/                          # 后端源码
│   ├── fastapi_app.py            # FastAPI 主入口（路由定义）
│   ├── config/
│   │   └── settings.py           # 全局配置（环境变量加载）
│   ├── db/
│   │   ├── mysql.py              # MySQL 操作（用户/角色/聊天记录）
│   │   └── redis.py              # Redis 操作（短期记忆/缓存）
│   ├── rag/
│   │   ├── embedding.py          # BGE-M3 文本向量化
│   │   ├── retrieval.py          # Milvus 向量检索
│   │   ├── chunking.py           # 文本分块
│   │   ├── rerank.py             # BGE-Reranker 重排序
│   │   ├── load_file.py          # 多格式文件加载（PDF/DOCX/PPT/IMG/TXT）
│   │   ├── load_pdf.py           # PDF 加载器（封装入口）
│   │   └── llm_chat.py           # 大模型对话接口
│   ├── utils/
│   │   └── logger.py             # 统一日志模块
│   ├── templates/
│   │   └── indexs.html           # 前端 SPA 页面
│   └── static/                   # 静态资源（CSS/JS）
├── data/                         # 知识库 PDF 数据
│   └── PDF数据集/
│       ├── 法律数据集/            # 中华人民共和国刑法.pdf
│       ├── 医疗数据集/            # 医疗门诊真实病例数据集.pdf
│       └── 心理专家数据集/        # 真实心理数据集.pdf
├── models/                       # 本地 AI 模型
│   └── BAAI/
│       ├── bge-m3/               # 嵌入模型
│       └── bge-reranker-base/    # 重排序模型
├── scripts/                      # 数据初始化脚本
│   ├── create_all_knowledge_bases.py  # 一键创建所有知识库
│   └── init_database.py              # 数据库初始化
├── tests/                        # 单元测试
│   ├── test_chat.py
│   ├── test_chunking.py
│   ├── test_embedding.py
│   ├── test_milvus.py
│   ├── test_mysql.py
│   ├── test_redis.py
│   ├── test_rerank.py
│   └── test_retrieval.py
├── nginx/                         # Nginx 配置备份
│   └── rag-roleplay.conf          # 前后端分离配置
├── docker-compose.yml            # Milvus 容器编排
├── requirements.txt              # Python 依赖清单
├── .env                          # 环境变量（不提交）
├── .env.example                  # 环境变量模板
├── simple_start.py               # 启动脚本
├── debug_start.py                # 诊断脚本
└── DEPLOYMENT.md                 # 本文档

# Nginx 前端部署目录
/var/www/rag-frontend/
├── indexs.html                   # 前端 SPA 页面
└── static/                       # 静态资源（CSS/JS）
```

---

## 8. API 接口列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 前端主页面 |
| POST | `/api/register` | 用户注册 `{phone, password, code}` |
| POST | `/api/login` | 用户登录 `{phone, password}` |
| GET | `/api/roles` | 获取角色列表 |
| GET | `/api/character/{role_id}` | 获取角色详情 |
| POST | `/api/user/role` | 更新用户当前角色 |
| POST | `/api/chat` | 核心聊天接口 `{user_id, role_id, message}` |
| POST | `/api/chat/send` | 前端兼容聊天接口 `{roleId, message}` |
| POST | `/api/sms/send` | 发送验证码 `{phone}` |
| POST | `/api/sms/verify` | 验证验证码 `{phone, code}` |

### 角色映射

| role_id | 角色 | 知识库 |
|---------|------|--------|
| `lawyer` | 刑事律师（林律） | law_rag |
| `psych` | 心理医生（张心理） | psychology_rag |
| `doctor` | 医疗门诊（刘医学） | medical_rag |

---

## 9. 部署步骤

### 9.1 首次部署

```bash
# 1. 安装系统依赖
yum install -y python3.10 python3.10-devel

# 2. 克隆项目
cd /root
git clone <repo-url> rag-project
cd rag-project

# 3. 创建虚拟环境
python3.10 -m venv venv
source venv/bin/activate

# 4. 安装 Python 依赖
pip install -r requirements.txt
# 注意：torch 需根据 CPU/GPU 单独安装
# CPU 版本：pip install torch --index-url https://download.pytorch.org/whl/cpu

# 5. 下载本地模型
pip install modelscope
python -c "
from modelscope import snapshot_download
snapshot_download('BAAI/bge-m3', cache_dir='./models')
snapshot_download('BAAI/bge-reranker-base', cache_dir='./models')
"

# 6. 配置环境变量
cp .env.example .env
vim .env  # 填入 API_KEY、MYSQL_PASSWORD 等

# 7. 启动依赖服务
docker-compose up -d        # Milvus + etcd + MinIO
systemctl start redis       # Redis
systemctl start mariadb     # MySQL/MariaDB

# 8. 初始化知识库（首次）
python scripts/create_all_knowledge_bases.py

# 9. 配置 Nginx 前后端分离
yum install -y nginx
cp nginx/rag-roleplay.conf /etc/nginx/conf.d/
mkdir -p /var/www/rag-frontend
cp -r src/templates/indexs.html /var/www/rag-frontend/
cp -r src/static /var/www/rag-frontend/
# 注释掉 /etc/nginx/nginx.conf 中的默认 server 块（避免端口冲突）
systemctl start nginx
systemctl enable nginx

# 10. 启动 FastAPI
python simple_start.py
```

### 9.2 日常运维

```bash
# 启动全部服务
systemctl start nginx
systemctl start rag-roleplay

# 停止
systemctl stop nginx
systemctl stop rag-roleplay

# 状态检查
curl http://localhost/              # Nginx 前端
curl http://localhost:8000/         # FastAPI 后端
ss -tlnp | grep -E ':80|:8000'

# 查看日志
tail -f /root/rag-project/src/logs/uvicorn.log
tail -f /var/log/nginx/access.log
```

### 9.3 健康检查

```bash
# Nginx 前端
curl -s -o /dev/null -w "%{http_code}" http://localhost/

# 应用健康（后端直连）
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/

# MySQL 连接
python -c "from src.db.mysql import get_mysql_connection; get_mysql_connection(); print('MySQL OK')"

# Redis 连接
python -c "from src.db.redis import get_redis_client; get_redis_client().ping(); print('Redis OK')"

# Milvus 连接
python -c "from src.rag.retrieval import client, collections; print('Milvus OK, collections:', collections)"
```

### 9.4 开机自启动

| 服务 | 管理方式 | 开机自启 |
|------|----------|----------|
| Nginx | systemd (enabled) | ✅ |
| FastAPI | systemd (rag-roleplay.service, enabled) | ✅ |
| Milvus | Docker Compose (restart: always) | ✅ |
| MariaDB | systemd (enabled) | ✅ |
| Redis | systemd (enabled) | ✅ |

系统重启后所有服务自动启动，无需手动干预。

---

## 10. 安全说明

| 项目 | 说明 |
|------|------|
| 密码存储 | SHA256 哈希，未加盐（生产环境建议升级为 bcrypt） |
| API 密钥 | 存储在 `.env`，已加入 `.gitignore` |
| Token | 当前为硬编码 `mock_token`（生产环境需实现 JWT） |
| SMS 验证 | 注册接口目前未校验验证码（生产环境需修复） |
| 数据库密码 | 建议使用强密码，避免默认值 `123456` |
| HTTPS | 当前为 HTTP，生产环境建议配置 Nginx 反向代理 + SSL |

---

## 11. 已知限制

1. **无 GPU**：模型推理在 CPU 上运行，向量嵌入速度较慢
2. **Milvus 一次性连接**：启动后 Milvus 不可用需重启应用
3. **连接池上限**：MySQL 连接池默认最大 5 连接
4. **Token 未实现 JWT**：当前使用 mock_token
5. **无请求限流**：未配置 rate limiting
6. **磁盘使用 80%**：建议清理不用的模型文件或扩容
7. **对话历史 TTL**：Redis 中对话历史 5 分钟过期，长时间对话可能丢失上下文

---

## 12. 故障排查

| 现象 | 可能原因 | 排查命令 |
|------|----------|----------|
| 页面打不开 | Nginx 或应用未启动 | `ss -tlnp \| grep -E ':80\|:8000'` |
| 聊天无回复 | API Key 错误 | `grep API_KEY .env` |
| 知识库无结果 | Milvus 未启动 | `docker ps \| grep milvus` |
| 注册失败 | MySQL 连接问题 | `python -c "from src.db.mysql import get_mysql_connection"` |
| 对话无记忆 | Redis 连接问题 | `redis-cli ping` |
| 模型加载失败 | 模型路径错误 | `ls models/BAAI/bge-m3/` |
| 端口不通 | 云安全组未放行 | 阿里云控制台 → ECS → 安全组 → 入方向添加 80 |

### 常见修复

```bash
# Milvus 不可用
docker-compose down && docker-compose up -d

# 数据库表损坏
python -c "from src.db.mysql import init_database; init_database()"

# 依赖版本冲突
pip install -r requirements.txt --force-reinstall

# 端口被占用
kill $(lsof -t -i:8000)
```
