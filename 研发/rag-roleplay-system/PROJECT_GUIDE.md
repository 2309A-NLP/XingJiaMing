# RAG 角色扮演系统 — 10分钟代码讲解

> 一次完整的 RAG 项目实战：从 PDF 知识库到多角色 AI 对话

---

## 目录

1. [项目是什么](#1-项目是什么)
2. [技术栈总览](#2-技术栈总览)
3. [系统架构图](#3-系统架构图)
4. [项目文件结构](#4-项目文件结构)
5. [逐文件逐函数详解](#5-逐文件逐函数详解)
6. [前后端连接方式](#6-前后端连接方式)
7. [日志系统实现](#7-日志系统实现)
8. [RAGAS 质量评估结果](#8-ragas-质量评估结果)
9. [压力测试结果](#9-压力测试结果)
10. [最近修复的 Bug](#10-最近修复的-bug)

---

## 1. 项目是什么

**一句话：** 用户选择一个角色（律师/心理医生/医生），输入问题 → 系统在 PDF 知识库里检索相关内容 → 把检索结果喂给 DeepSeek 大模型 → 模型按照角色人设生成专业回复。

### 1.1 三个角色

| 角色 | role_id | 知识库 | 风格 |
|------|---------|--------|------|
| 林律（刑事律师） | lawyer | 刑法 PDF | 专业严谨，引用法条 |
| 张心理（心理医生） | psych | 心理学 PDF | 温暖共情，引导式提问 |
| 刘医学（医疗门诊） | doctor | 医疗病例 PDF | 科学客观，分点说明 |

### 1.2 一句话流程

```
用户输入 → BGE-M3 转向量 → Milvus 检索 top5 → BGE-Reranker 精排 top3
    → 拼接 System Prompt → DeepSeek API 生成回复 → 返回前端
```

---

## 2. 技术栈总览

### 2.1 后端

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.10 | 运行环境 |
| FastAPI | 0.110.0 | Web 框架，定义 API 路由 |
| Uvicorn | 0.29.0 | ASGI 服务器，运行 FastAPI |
| PyMySQL | 1.4.6 | MySQL 数据库驱动 |
| Redis (redis-py) | 5.0.3 | 缓存 + 对话短期记忆 |
| pymilvus | 2.4.4 | Milvus 向量数据库客户端 |
| bcrypt | 4.x | 密码安全哈希 |
| slowapi | 最新 | API 限流 (200 req/min 全局) |
| PyJWT | 2.x | JWT Token 生成/验证 |

### 2.2 AI 模型

| 模型 | 位置 | 维度 | 用途 |
|------|------|------|------|
| BGE-M3 | `models/BAAI/bge-m3/` | 1024 | 文本 → 向量（嵌入） |
| BGE-Reranker | `models/BAAI/bge-reranker-base/` | — | 检索结果重排序 |
| DeepSeek V4-Flash | 远程 API | — | 最终回复生成 |

### 2.3 基础设施

| 组件 | 端口 | 部署方式 |
|------|------|----------|
| Nginx | 80 | 反向代理 + 静态文件 |
| MySQL (MariaDB) | 3306 | systemd 自启 |
| Redis | 6379 | systemd 自启 |
| Milvus | 19530 | Docker Compose |
| FastAPI | 8000 | systemd (rag-roleplay.service) |

### 2.4 前端

- **纯 HTML + CSS + Vanilla JS**（无框架 SPA）
- Tailwind CSS (CDN) 样式
- 四个页面：登录 / 注册 / 角色选择 / 聊天
- `ApiService` 封装所有 API 调用

---

## 3. 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户浏览器                                │
│  http://120.26.32.90 — 前端 SPA (indexs.html + Tailwind CSS)    │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  Nginx (port 80)                                                │
│  ├── /api/*     → proxy_pass http://127.0.0.1:8000 (后端API)   │
│  ├── /static/*  → alias /var/www/rag-frontend/static/          │
│  └── /          → try_files indexs.html (前端页面)              │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  Uvicorn (port 8000, 2 workers)                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  FastAPI App (src/fastapi_app.py)                         │  │
│  │                                                           │  │
│  │  API 路由:                                                │  │
│  │  POST /api/register  → 注册                               │  │
│  │  POST /api/login     → 登录 (返回 JWT Token)              │  │
│  │  GET  /api/roles     → 角色列表                           │  │
│  │  POST /api/chat      → ★ 核心聊天 (RAG + LLM)            │  │
│  │  ...其他路由                                               │  │
│  │                                                           │  │
│  │  中间件:                                                   │  │
│  │  ├── CORS 中间件 (允许前端跨域)                            │  │
│  │  ├── 请求日志中间件 (记录所有请求 + 耗时)                  │  │
│  │  ├── 全局异常捕获 (try/except 兜底, 写 error.log)         │  │
│  │  └── 全局限流 (200 req/min)                               │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────┬───────────────────────────────────────┘
                          │
    ┌─────────────────────┼──────────────────────────┐
    │                     │                          │
    ▼                     ▼                          ▼
┌────────────┐    ┌────────────┐    ┌──────────────────────┐
│  MySQL     │    │  Redis     │    │  Milvus (Docker)     │
│  :3306     │    │  :6379     │    │  :19530              │
│            │    │            │    │                      │
│  users     │    │  chat:u:r  │    │  law_rag (1024维)   │
│  characters│    │  (TTL 300s)│    │  medical_rag         │
│  chat_his- │    │  sms_code  │    │  psychology_rag      │
│  tory      │    │  (TTL 300s)│    │                      │
└────────────┘    └────────────┘    └──────────────────────┘
       │                                       │
       └──────────────────┬────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  本地模型推理 (CPU)                                             │
│  ├── BGE-M3:       embed_query(文本) → 1024维向量             │
│  └── BGE-Reranker: rerank(问题, 文档列表) → 排序后的文档列表   │
│                                                                 │
│  在线 API:                                                      │
│  └── DeepSeek V4-Flash: chat(系统提示 + 用户问题) → 回复       │
└─────────────────────────────────────────────────────────────────┘
```

### 核心聊天流程

```
POST /api/chat {user_id, role_id, message}
  │
  ├─ Step 1: 解析参数 → role_id="lawyer" → character_id=1
  │
  ├─ Step 2: 查角色信息 → MySQL characters 表
  │   → 角色名: "林律", prompt: "你是一位专业刑事律师..."
  │   → 知识库: "law"
  │
  ├─ Step 3: 取对话历史 → Redis key="chat:{user_id}:{role_id}"
  │   → "用户：...\n助手：..."
  │
  ├─ Step 4: 检索知识库
  │   ├─ embed_query("盗窃罪怎么判") → [0.12, -0.34, ...] (1024维)
  │   ├─ search_vector(vec, "law_rag", top_k=5) → 5条相似文本
  │   ├─ rerank(query, docs) → 按相关性排序取 top3
  │   └─ 判断是否相关（L2距离 < 1.0）
  │
  ├─ Step 5: 构建 System Prompt
  │   ├─ 有相关知识 → 知识库增强模式（回答基于知识库）
  │   └─ 无相关知识 → 自由对话模式（角色正常聊天）
  │
  ├─ Step 6: 调用 DeepSeek API → 生成回复
  │
  ├─ Step 7: 保存对话
  │   ├─ Redis (短期, TTL 300s)
  │   └─ MySQL (持久化)
  │
  └─ Step 8: 返回 {"success": true, "message": "根据《刑法》第264条..."}
```

---

## 4. 项目文件结构

```
/root/rag-project/
│
├── src/                              ★ 后端源码
│   ├── fastapi_app.py                ★ FastAPI 主入口, 所有 API 路由 + RAG 管线
│   ├── config/
│   │   └── settings.py               ★ 全局配置 (.env + 默认值)
│   ├── db/
│   │   ├── mysql.py                  ★ MySQL 操作 (用户/角色/聊天记录)
│   │   └── redis.py                  ★ Redis 操作 (短期记忆/缓存)
│   ├── rag/
│   │   ├── embedding.py              ★ BGE-M3 文本→1024维向量
│   │   ├── retrieval.py              ★ Milvus 向量检索
│   │   ├── chunking.py               文本分块
│   │   ├── rerank.py                 ★ BGE-Reranker 重排序
│   │   ├── llm_chat.py               LLM 对话接口 (被 fastapi_app 替代)
│   │   ├── load_file.py              多格式文件加载
│   │   └── load_pdf.py               PDF 加载
│   ├── utils/
│   │   ├── logger.py                 ★ 统一日志系统 (app.log + error.log + json.log)
│   │   └── auth.py                   ★ JWT Token 生成/验证
│   ├── templates/
│   │   └── indexs.html               ★ 前端 SPA 页面 (登录/注册/角色/聊天)
│   └── static/                       CSS/JS 静态资源
│
├── src/logs/                         日志文件目录
│   ├── app.log                       所有请求日志 (按天轮转, 保留30天)
│   ├── error.log                     ERROR+ 级别错误 (新增)
│   └── app.json.log                  JSON 结构化日志 (供 ELK 采集)
│
├── tests/                            测试文件
│   ├── test_ragas.py                 ★ RAGAS 质量评估脚本
│   ├── ragas_results.json            ★ 15 题评估结果 (含逐题数据)
│   ├── test_*.py                     单元测试
│   └── stress_test.py                压力测试脚本
│
├── data/PDF数据集/                    知识库源 PDF 文件
│   ├── 法律数据集/刑法.pdf
│   ├── 医疗数据集/病例.pdf
│   └── 心理专家数据集/心理.pdf
│
├── models/BAAI/                      本地 AI 模型
│   ├── bge-m3/                       BGE-M3 嵌入模型
│   └── bge-reranker-base/            BGE-Reranker 重排序模型
│
├── scripts/                          初始化脚本
│   ├── create_all_knowledge_bases.py  一键创建所有 Milvus 集合
│   └── init_database.py               数据库建表
│
├── nginx/rag-roleplay.conf           Nginx 配置备份
├── docker-compose.yml                Milvus 容器编排
├── requirements.txt                  Python 依赖清单
├── .env                              环境变量 (不提交)
├── PROJECT_GUIDE.md                  本文档
└── DEPLOYMENT.md                     部署运维文档
```

---

## 5. 逐文件逐函数详解

### 5.1 `src/config/settings.py` — 全局配置中心

**作用：** 读取 `.env` 文件，提供整个项目所有配置。

```python
# 关键配置项
LLM_CONFIG = {
    "api_key": "...",      # DeepSeek API 密钥
    "api_url": "...",      # https://api.deepseek.com
    "model": "deepseek-v4-flash",
    "temperature": 0.7,    # 生成随机性
    "max_tokens": 1024,    # 最大回复长度
    "timeout": 60          # API 超时秒数
}

MILVUS_CONFIG = {
    "host": "...", "port": 19530,
    "dim": 1024,           # 向量维度 (BGE-M3)
    "collection_name": "law_rag"  # 默认集合
}

RAG_CONFIG = {
    "chunk_size": 512,     # 文本分块大小
    "top_k": 10,           # 初始召回数
    "rerank_top_k": 3      # 精排后保留数
}
```

---

### 5.2 `src/db/mysql.py` — MySQL 数据库操作

#### 类 `ConnectionPool` — 线程安全的连接池

| 方法 | 功能 | 关键细节 |
|------|------|----------|
| `get_connection()` | 从池取连接 / 创建新连接 | 锁内增减 active_count，锁外创建连接；失败回减避免泄漏 |
| `return_connection()` | 归还连接到池 | 超量则关闭 |

**修复了连接池泄漏 Bug：** 之前创建连接失败时 `active_count` 不回减，导致池耗尽。现在 `try/except` 中 `active_count -= 1`。

#### 函数清单

| 函数 | 参数 | 返回值 | 功能 |
|------|------|--------|------|
| `_hash_password(pwd)` | str | str | bcrypt 哈希 (cost=12) |
| `_verify_password(pwd, hash)` | str, str | bool | 验证密码 (自动兼容旧 SHA256) |
| `init_database()` | — | None | 建表 (users/characters/chat_history) + 初始化 3 个角色 |
| `register_user(phone, password)` | str, str | bool | 注册新用户 (检查重复→bcrypt哈希→插入) |
| `authenticate_user(phone, password)` | str, str | dict | 登录验证 (返回 `{id, username}` 或 `{error}`)；自动升级旧 SHA256→bcrypt |
| `get_user_by_id(user_id)` | int | dict/None | 根据 ID 查用户 |
| `get_character_info(id=1)` | int | dict | 查角色详情 (MySQL 失败则返回硬编码默认) |
| `get_all_characters()` | — | list | 获取所有角色列表 |
| `save_chat_message(uid, cid, role, content)` | ... | None | 保存聊天记录到 MySQL |
| `get_chat_history(uid, cid, limit=10)` | ... | list | 取最近聊天记录 (按时间正序) |
| `format_chat_history(history)` | list | str | 格式化聊天记录 → Prompt 文本 |
| `update_user_role(uid, role_id)` | int, str | bool | 更新用户当前角色 |

#### 数据库表

```sql
users:         id, phone(UNIQUE), name, password(bcrypt), role, created_at
characters:    id, name, role_type, description, prompt_template, knowledge_base
chat_history:  id, user_id(FK), character_id(FK), role, content, created_at
```

---

### 5.3 `src/db/redis.py` — Redis 缓存操作

| 函数 | 功能 | 数据结构 |
|------|------|----------|
| `get_redis_client()` | 延迟初始化 Redis 连接 | — |
| `save_message(uid, rid, role, content)` | 保存消息到列表 + 控制长度 + 设 TTL | `chat:{uid}:{rid}` → List, TTL=300s |
| `get_history(uid, rid)` | 取格式化对话历史 | "用户：xxx\n助手：xxx" |
| `clear_history(uid, rid)` | 删除键 | — |

**Redis Key 设计：**
```
chat:{user_id}:{role_id}     →  List  (对话历史, TTL 300s)
sms_code:{phone}             →  String (验证码, TTL 300s)
```

---

### 5.4 `src/rag/embedding.py` — BGE-M3 文本向量化

#### 函数清单

| 函数 | 功能 | 内部流程 |
|------|------|----------|
| `check_gpu_availability()` | 检测 GPU (优先 cuda:0, 否则 cpu) | `torch.cuda.is_available()` |
| `load_model_with_memory_optimization()` | 加载 BGE-M3 模型 + 分词器 | GPU→半精度 / CPU→全精度 / OOM→自动降级 |
| `embed_query(text)` | **单文本 → 1024维向量** | tokenizer → model → CLS token → L2归一化 |
| `embed_texts(texts, batch_size=32)` | 批量文本 → 向量列表 | 分批推理 → 收集结果 |

**`embed_query()` 核心代码：**
```python
def embed_query(text):
    inputs = tokenizer(text, return_tensors="pt", padding=True,
                       truncation=True, max_length=256).to(device)
    with torch.no_grad():
        outputs = model(**inputs)
    embedding = outputs.last_hidden_state[:, 0, :]  # CLS token
    embedding = F.normalize(embedding, p=2, dim=1)   # L2归一化
    return embedding[0]  # shape: [1024]
```

---

### 5.5 `src/rag/retrieval.py` — Milvus 向量检索

| 函数 | 功能 | 关键参数 |
|------|------|----------|
| `test_port(host, port)` | 测试端口连通性 | timeout=2s |
| `connect_milvus_with_retry()` | 连接 Milvus (最多重试3次) | 失败时 `milvus_available=False` |
| `search_vector(vector, collection, top_k=5)` | **向量相似搜索** | L2 距离, 输出: `[{id, distance, entity:{text}}]` |
| `insert_vectors(vectors, texts, collection)` | 批量插入向量 (建库用) | — |
| `create_collection(name, dim=1024)` | 创建集合 (如不存在) | metric_type="L2" |

#### 全局变量

| 变量 | 初始值 | 用途 |
|------|--------|------|
| `client` | None | Milvus 客户端实例 |
| `milvus_available` | False | 是否可用 (下游据此降级) |
| `collections` | [] | 可用集合列表 |

**注意：** 模块加载时自动调用 `connect_milvus_with_retry()`。如果 Milvus 不可用，系统降级为"无知识库"模式。

---

### 5.6 `src/rag/rerank.py` — BGE-Reranker 重排序

| 函数 | 功能 |
|------|------|
| `_lazy_load()` | 延迟加载 BGE-Reranker 模型 (首次调用时加载) |
| `rerank(query, docs)` | 计算 query 与每个 doc 的相关性分数 → 按分降序排列 |

**`rerank()` 核心逻辑：**
```python
def rerank(query, docs):
    _lazy_load()
    pairs = [(query, doc) for doc in docs]
    inputs = tokenizer(pairs, padding=True, truncation=True,
                       return_tensors="pt").to(device)
    with torch.no_grad():
        scores = model(**inputs).logits.flatten().tolist()
    result = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
    return [doc for doc, _ in result]
```

---

### 5.7 `src/rag/chunking.py` — 文本分块

| 函数 | 功能 |
|------|------|
| `clean_text(text)` | 清理多余空白 (多个空格→单个) |
| `chunk_text(text, max_len=500)` | 固定长度滑动切分，chunk_size=512, overlap=50 |

---

### 5.8 `src/rag/llm_chat.py` — 大模型对话接口

| 函数 | 功能 |
|------|------|
| `chat_with_llm(messages, model)` | 通用 LLM 调用 (OpenAI 兼容格式) |
| `chat_with_law(query, law_context, history)` | 法律领域专用对话 (已较少使用，被 fastapi_app 内联替代) |

---

### 5.9 `src/rag/load_file.py` — 多格式文件加载

支持 PDF/DOCX/PPT/图片/TXT/MD 六种格式，通过扩展名自动选择加载器。

| 函数 | 功能 |
|------|------|
| `load_file(path)` | 根据扩展名自动选择加载器 (统一入口) |
| `load_pdf(path)` → `load_pdf_with_ocr()` | PDF 文本提取 (含 OCR 降级) |
| `load_docx(path)` | Word 文档读取 |
| `load_ppt(path)` | PowerPoint 读取 |
| `load_image(path)` | 图片 OCR |
| `load_txt(path)` | 文本文件 (自动检测编码) |
| `load_md(path)` | Markdown 文件 |

---

### 5.10 `src/fastapi_app.py` — ★ 应用主入口（核心）

#### 依赖注入

```python
# 请求体模型 (Pydantic)
class RegisterRequest:  phone, password, code
class LoginRequest:     phone, password
class ChatRequest:      user_id, role_id, message
```

#### 路由清单

| 路由 | 方法 | 函数 | 功能 | 限流 |
|------|------|------|------|------|
| `/` | GET | `index()` | 返回前端 HTML | 无 |
| `/api/health` | GET | `health_check()` | 健康检查 (MySQL/Redis/Milvus/LLM) | 无 |
| `/api/register` | POST | `register()` | 注册 | 10/min |
| `/api/login` | POST | `login()` | 登录 (返回 JWT Token) | 20/min |
| `/api/roles` | GET | `get_roles_api()` | 获取角色列表 | 无 |
| `/api/character/{role_id}` | GET | `get_character()` | 获取角色详情 | 无 |
| `/api/user/role` | POST | `update_role()` | 切换用户角色 | 无 |
| `/api/chat` | POST | `chat()` | **核心聊天 (非流式)** | 无 |
| `/api/chat/stream` | POST | `chat_stream()` | **SSE 流式聊天** | 无 |
| `/api/chat/send` | POST | `chat_send()` | **前端兼容聊天** | 无 |
| `/api/sms/send` | POST | `send_sms()` | 发送验证码 | 3/min |
| `/api/sms/verify` | POST | `verify_sms()` | 验证验证码 | 无 |

#### 内部函数详解

| 函数 | 功能 | 关键逻辑 |
|------|------|----------|
| `_llm_chat(prompt, question)` | 调用 LLM (带指数退避重试) | 最多重试2次，间隔 1s→2s |
| `_build_chat_prompt(...)` | **构建 System Prompt (双模式)** | 有知识库→增强模式，无→自由对话；注入用户名 |
| `_retrieve_knowledge(question, kb)` | **RAG 检索 + 相关性判断** | 返回 `(知识文本, 是否相关)`，L2距离<1.0 算相关 |
| `_run_chat_pipeline(uid, rid, q)` | **核心管线 (8步)** | 查角色→取历史→检索→构建Prompt→LLM→存历史→返回 |

#### `_build_chat_prompt()` — 双模式 Prompt

```python
# 模式1: 有相关知识 → 知识库增强模式
"""你现在是林律，专注刑事辩护...你正在和{用户名}对话。
【参考知识库内容】
{检索到的法律条文}
【回答要求】
1. 专业问题优先参考知识库
2. 没有相关信息可结合自己的知识
3. 非专业问题正常回答"""

# 模式2: 无相关知识 → 自由对话模式
"""你现在是林律，专注刑事辩护...你正在和{用户名}对话。
【回答要求】
1. 用角色身份自然地对话
2. 保持专业语气"""
```

**修复前**的 Prompt 强制"必须基于知识库回答"，导致问"我叫什么"时回复"不在知识范围内"。

---

### 5.11 `src/utils/logger.py` — 统一日志系统

详见 [第7节 日志系统实现](#7-日志系统实现)

---

### 5.12 `src/utils/auth.py` — JWT 认证

| 函数 | 功能 |
|------|------|
| `create_access_token(user_id, phone, username)` | 生成 JWT Token (过期时间 3天) |
| `get_current_user(request)` | 从请求头解析 Token → 返回当前用户 |
| `get_optional_user(request)` | 同上，但 Token 不存在时不报错 |

---

## 6. 前后端连接方式

### 6.1 架构：前后端完全分离

```
用户浏览器                              Nginx (80)
    │                                      │
    ├── 直接请求 / ──────────────────────→ 返回 indexs.html (前端 SPA)
    ├── 直接请求 /static/* ─────────────→ 返回 CSS/JS 静态文件
    └── AJAX 请求 /api/* ──────────────→ proxy_pass → FastAPI (8000)
```

### 6.2 API 调用方式

前端使用 `ApiService` 对象封装所有请求：

```javascript
// 前端 JS (indexs.html)
const ApiService = {
    baseUrl: window.location.origin + '/api',

    // 登录
    async login(phone, password) {
        return fetch(`${this.baseUrl}/login`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({phone, password})
        }).then(r => r.json());
    },

    // 获取角色列表
    async getRoles() {
        return fetch(`${this.baseUrl}/roles`).then(r => r.json());
    },

    // 发送聊天消息
    async sendMessage(roleId, message) {
        return fetch(`${this.baseUrl}/chat/send`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({roleId, message})
        }).then(r => r.json());
    }
};
```

### 6.3 数据流示例

```
登录页面:
  用户输入手机号 + 密码
    → fetch POST /api/login {phone, password}
    → FastAPI 验证 MySQL users 表
    → 返回 {success, token, user}
    → 前端保存 token 到 STATE, 跳转角色选择

聊天:
  用户输入 "盗窃罪怎么判"
    → fetch POST /api/chat/send {roleId: "lawyer", message: "盗窃罪怎么判"}
    → FastAPI RAG 管线 (向量检索 + LLM)
    → 返回 {code: 200, data: {reply: "根据《刑法》第264条..."}}
    → 前端渲染到聊天界面
```

### 6.4 角色映射 (前端 ↔ 后端)

```
前端 roleId: "lawyer"  →  role_map["lawyer"]  →  character_id=1  →  MySQL characters 表
前端 roleId: "psych"   →  role_map["psych"]   →  character_id=2  →  MySQL characters 表
前端 roleId: "doctor"  →  role_map["doctor"]  →  character_id=3  →  MySQL characters 表
```

---

## 7. 日志系统实现

### 7.1 设计目标

- 所有模块的日志**统一捕获**，不遗漏
- 自动按天轮转，保留 30 天
- 错误日志单独存放，方便排查
- 支持 JSON 结构化输出（供 ELK 采集）

### 7.2 架构设计

```
日志处理器挂载到 ROOT Logger（保证所有模块都能捕获）
       │
       ├── TimedRotatingFileHandler → /src/logs/app.log (INFO+)
       ├── TimedRotatingFileHandler → /src/logs/error.log (ERROR+)
       ├── TimedRotatingFileHandler → /src/logs/app.json.log (INFO+, JSON格式)
       └── StreamHandler → 控制台输出
```

**关键设计：** 不把处理器挂在模块各自的 logger 上，而是挂在 **root logger** 上。这样不管模块用 `get_logger(__name__)` 还是 `logging.getLogger(xxx)` 创建 logger，日志都会传播到 root 并被写入文件。

### 7.3 核心代码

```python
# src/utils/logger.py

def get_logger(name: str) -> logging.Logger:
    """获取统一配置的 logger（推荐所有模块使用）"""
    _init_root_logger()
    return logging.getLogger(name)

def _init_root_logger():
    """给 root logger 挂载所有处理器（只执行一次）"""
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # 文本日志 (INFO+) — 按天轮转, 保留30天
    h = TimedRotatingFileHandler(app.log, when="midnight", backupCount=30)
    h.setFormatter("[%(asctime)s] [%(levelname)s] [%(module)s:%(lineno)d] %(message)s")

    # 错误日志 (ERROR+) — 只记错误
    h = TimedRotatingFileHandler(error.log, when="midnight", backupCount=30)
    h.setLevel(logging.ERROR)

    # JSON 日志 (INFO+) — 结构化格式
    h = TimedRotatingFileHandler(app.json.log, when="midnight", backupCount=30)
    h.setFormatter(StructuredFormatter())  # → {"timestamp": "...", "level": "ERROR", ...}
```

### 7.4 日志文件内容示例

**app.log（文本格式）：**
```
[2026-05-07 10:16:16] [INFO] [logger:130] REQUEST POST /api/login -> 200 (268ms) [user=-]
[2026-05-07 10:16:16] [INFO] [logger:130] REQUEST GET /api/roles -> 200 (1ms) [user=-]
```

**error.log（错误专用）：**
```
[2026-05-07 10:15:42] [ERROR] [mysql:277] 验证用户异常：连接池耗尽，请稍后重试
[2026-05-07 10:16:49] [ERROR] [fastapi_app:95] Unhandled exception: POST /api/chat/send
Traceback (most recent call last):
  File "...", line ..., in chat_send
    ...
```

**app.json.log（JSON 格式，供 ELK 采集）：**
```json
{"timestamp": "2026-05-07T02:16:16.463631Z", "level": "INFO", "logger": "api.request",
 "message": "REQUEST POST /api/login -> 200 (268ms) [user=-]",
 "module": "logger", "function": "log_request", "line": 130,
 "extra": {"method": "POST", "path": "/api/login", "status": 200, "duration_ms": 267.5}}
```

### 7.5 全局异常捕获

在 FastAPI 中间件中做了兜底：

```python
@app.middleware("http")
async def request_logging_middleware(request, call_next):
    start = time.monotonic()
    try:
        response = await call_next(request)
    except Exception as exc:
        # 所有未捕获异常集中记录 + 写 error.log
        logger.error(f"Unhandled exception: {request.method} {request.url.path}\n"
                     f"{traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"message": "服务器内部错误"})
    # 记录请求日志
    log_request(request.method, request.url.path, response.status_code, duration_ms)
```

### 7.6 模块中使用方式

```python
from src.utils.logger import get_logger

logger = get_logger(__name__)  # 自动获得所有处理器

logger.info("请求成功")              # → app.log + app.json.log
logger.error("连接失败", exc_info=True)  # → app.log + app.json.log + error.log
```

---

## 8. RAGAS 质量评估结果

### 8.1 评估配置

| 项目 | 值 |
|------|-----|
| 评估时间 | 2026-05-06 |
| 评估框架 | RAGAS (官方库 v0.4.3) |
| 裁判 LLM | DeepSeek V4-Flash |
| 嵌入模型 | BGE-M3 (CPU) |
| 测试样本 | 3 角色 × 5 题 = 15 题 |
| 评估方式 | ground_truth 作为上下文 |

### 8.2 各项指标含义

| 指标 | 含义 | 公式 |
|------|------|------|
| **Faithfulness** (忠实度) | 回答是否基于给定上下文，有无幻觉 | 回答中的每个声明 → 是否可在上下文中找到 |
| **AnswerRelevancy** (回答相关性) | 回答是否切题 | 回答 → 生成反向问题 → 与原问题计算余弦相似度 |
| **ContextPrecision** (上下文精确度) | 检索文档中相关内容的比例 | 相关文档在排序中的位置加权 |
| **ContextRecall** (上下文召回率) | 标准答案中的信息是否被检索覆盖 | 标准答案中的每个声明 → 是否在检索文档中 |

### 8.3 总体得分

| 指标 | 平均分 | 评估 |
|------|--------|------|
| Faithfulness | **0.49** | ⚠️ 有改进空间 |
| AnswerRelevancy | **0.83** | ✅ 良好 |
| ContextPrecision | **1.00** | ✅ 满分 (使用 ground_truth) |
| ContextRecall | **1.00** | ✅ 满分 (使用 ground_truth) |
| **RAGAS Score** | **0.83** | ✅ 优秀 |

### 8.4 按角色汇总

| 角色 | Faithfulness | AnswerRelevancy | ContextPrecision | ContextRecall | 综合 |
|------|-------------|-----------------|------------------|---------------|------|
| 林律（刑事律师） | **0.65** | 0.74 | 1.00 | 1.00 | 0.85 |
| 张心理（心理医生） | **0.45** | 0.89 | 1.00 | 1.00 | 0.83 |
| 刘医学（医疗门诊） | **0.42** | 0.87 | 1.00 | 1.00 | 0.82 |

### 8.5 逐题明细

| # | 角色 | 问题 | Faith. | AnsRel | 分析 |
|---|------|------|--------|--------|------|
| 1 | 林律 | 盗窃罪的量刑标准是什么？ | 0.73 | 0.81 | 法条引用准确 |
| 2 | 林律 | 正当防卫的构成要件有哪些？ | 0.57 | 0.99 | 回答全面，但稍有发挥 |
| 3 | 林律 | 故意伤害罪和过失致人重伤罪的区别？ | N/A | 0.00 | **空回答** (LLM 拒绝回答) |
| 4 | 林律 | 缓刑的适用条件是什么？ | 0.70 | 0.95 | 回答准确 |
| 5 | 林律 | 自首和坦白有什么区别？ | 0.59 | 0.95 | 核心区别正确 |
| 6 | 张心理 | 如何缓解焦虑情绪？ | 0.04 | 0.92 | **Faithfulness 极低** — LLM 自由发挥太多 |
| 7 | 张心理 | 抑郁症的常见症状有哪些？ | 0.80 | 0.90 | 回答贴近上下文 |
| 8 | 张心理 | 如何帮助有心理困扰的朋友？ | 0.09 | 0.80 | 同上，过度展开 |
| 9 | 张心理 | 什么是认知行为疗法？ | **1.00** | 0.84 | 严格复述上下文，满分 |
| 10 | 张心理 | 压力过大会导致哪些身体反应？ | 0.31 | 0.98 | 回答相关但超出上下文 |
| 11 | 刘医学 | 高血压患者日常生活需要注意什么？ | 0.35 | 0.78 | 展开较多 |
| 12 | 刘医学 | 糖尿病的典型症状和诊断标准？ | **1.00** | 0.90 | 严格复述，满分 |
| 13 | 刘医学 | 感冒和流感怎么区分？ | 0.38 | 0.79 | 超出上下文展开 |
| 14 | 刘医学 | 如何预防心血管疾病？ | 0.07 | 0.92 | Faithfulness 很低 |
| 15 | 刘医学 | 儿童发热应该怎么处理？ | 0.29 | 0.95 | 基本正确但展开多 |

### 8.6 关键发现

1. **Faithfulness (0.49) 偏低** — DeepSeek 倾向于展开解释和添加礼貌用语，而非严格复述上下文
2. **法律角色最高** (0.65) — 法条精确性要求高，LLM 更小心
3. 部分 Faithfulness 极低 (如 #6=0.04, #14=0.07) — LLM 大量使用自己的知识而非提供上下文
4. **ContextPrecision/Recall 满分** — 因为评估时用 ground_truth 替代了真实检索结果
5. 题 #3 空回答 — LLM 可能触发了安全策略

### 8.7 改进方向

- 调低 temperature (当前 0.3 → 可降至 0.1)
- Prompt 更严格约束"只基于下面提供的内容回答"
- 填充真实 Milvus 知识库后重新评估
- 对 #3 排查 LLM 安全策略触发原因

### 8.8 复现评估

```bash
source venv/bin/activate

# 全量评估 (15题, ~2小时)
python tests/test_ragas.py

# 快速模式 (6题, ~30分钟)
python tests/test_ragas.py --quick

# 单角色
python tests/test_ragas.py --role lawyer
```

---

## 9. 压力测试结果

### 9.1 轻量接口 (GET Roles / Character / Login)

| 测试 | 并发 | QPS | P50 | 错误率 |
|------|------|-----|-----|--------|
| GET /api/roles | 20 | **663** | 29ms | 0% |
| GET /api/roles | 100 | **750** | 77ms | **0%** |
| POST /api/login | 50 | **683** | 62ms | 0% |
| POST /api/sms/send | 20 | **844** | 20ms | 0% |

### 9.2 聊天接口 (POST /api/chat) — LLM 是瓶颈

| 测试 | 请求数 | 并发 | QPS | P50 | 成功率 |
|------|--------|------|-----|-----|--------|
| Chat 混合角色 | 10 | 3 | **0.04** | 77.7s | **100%** |
| Chat 真实15题 | 15 | 3 | **0.04** | 87.5s | **100%** |
| Chat 同问题×50 | 50 | 5 | 0.05 | 84.1s | **70%** |

### 9.3 核心结论

- 轻量接口稳定 **650~750 QPS**，零错误
- 聊天接口受 DeepSeek API 推理时间制约，P50=84s
- **并发 3 以下 100% 成功，并发 5 以上 30% 失败**

---

## 10. 最近修复的 Bug

### Bug 1: 问"我叫什么" → 回复"不在知识范围内"

**原因：** `_build_chat_prompt()` 的 Prompt 强制"回答必须完全基于【知识库内容】"，导致所有非知识库问题都被拒绝。

**修复：** 改为**双模式 Prompt**：
- 知识库相关 (L2距离<1.0) → 增强模式，参考知识库
- 知识库无关 → 自由对话模式，角色正常聊天

同时**注入用户名**到 Prompt，让 LLM 知道在和谁说话。

### Bug 2: 注册后登录不上，多点几次才行

**原因：** 两个连环 bug：
1. **连接池泄漏** — `get_connection()` 创建连接失败时 `active_count` 不回减，池逐渐耗尽
2. **事务快照** — 连接归还时未 `rollback`，MySQL 事务快照导致看不到新数据

**修复：** `get_connection()` 中 `try/except` 回减 `active_count` + `finally` 中强制 `rollback()` 清理事务状态。

### Bug 3: 登录错误信息模糊

**原因：** `authenticate_user()` 把连接池耗尽等所有异常吞掉返回 `None`，登录接口统一显示"手机号或密码错误"。

**修复：** 区分返回 `{error: "手机号未注册"}` / `{error: "密码错误"}` / `{error: "系统繁忙，请稍后重试"}`。

### Bug 4: 日志系统各模块不统一

**原因：** `fastapi_app.py` 自己创建 `logging.getLogger(__name__)`，与 `logger.py` 的 `RAG_SYSTEM` 日志器不互通，导致部分日志丢失。

**修复：** 所有处理器挂到 **root logger**，所有模块通过 `get_logger(__name__)` 获取统一配置的记录器。新增 `error.log` 专门记录 ERROR 级别错误。

---

> **最后更新：** 2026-05-07 | **仓库：** git@github.com:SWCQYBZ/rag-roleplay-system.git
