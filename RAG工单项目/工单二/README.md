# RAG 问答系统 - 工单2

**工单编号**：人工智能 NLP-RAG-基于 PDF 文档的问答系统

## 项目简介

基于大语言模型（LLM）的 RAG 问答系统，在工单1基础上进行了全面优化，重点提升**检索准确率**、**响应速度**和**系统稳定性**。

### 核心优化（相比工单1）

| 优化项 | 工单1 | 工单2 | 效果 |
|--------|-------|-------|------|
| BM25 分词 | 字符级 | jieba 分词 + 停用词过滤 | 中文检索准确率大幅提升 |
| 多路融合 | hit_count 排序 | RRF 倒数排名融合（k=60） | 双路命中结果排名更合理 |
| Rerank 精排 | 关闭 | bge-reranker-base（GPU 加速 + 智能跳过） | 精排 <0.5s，节省 1-2s |
| 分块策略 | 固定字符切割 | 表格保护 + 按句子边界分块 + 重叠 | 语义完整性更好 |
| 生成 Prompt | 简单指令 | 5 条硬规则 + temperature 0.1 | 端到端准确率 72% → 90% |
| 查询缓存 | 无 | 内存缓存（TTL 300s，最多 200 条） | 重复查询 0.01s 响应 |
| 简单问题优化 | 无 | 跳过 Query Understanding | 简单问题省 2-3s |
| 并行检索 | 串行 | Query 理解 + Embedding 并行执行 | 节省 1-2s |
| Embedding | CPU | GPU (CUDA) | 编码速度提升 5x |
| 容错机制 | 基础 | 输入校验 + LLM 重试 + 限流 + 统一异常处理 | 生产级稳定性 |
| 多语言 | 无 | 中英文双向翻译（气泡翻译按钮） | 用户体验优化 |
| 端口冲突 | 手动处理 | 启动时自动检测并清理占用端口 | 一键启动无障碍 |

### 端到端准确率

```
评测结果：9/10（90.0%）达标
首 token 响应：~3s（专业问题）/ ~1s（问候语）
重复查询：0.01s（缓存命中）
3秒内占比：80%
```

### 技术栈

- **后端**：FastAPI + Python 3.10
- **前端**：React + TypeScript + Vite
- **向量数据库**：Milvus（Docker）
- **Embedding 模型**：BGE-M3（GPU / CUDA）
- **Rerank 模型**：bge-reranker-base（GPU / CUDA）
- **LLM**：DeepSeek-Chat（API）
- **PDF 解析**：MinerU + PaddleOCR
- **中文分词**：jieba

## 快速开始

### 环境要求
- Python 3.10+（项目自带 `.venv`）
- Node.js 18+
- Milvus（localhost:19530）
- NVIDIA GPU（CUDA，用于 Embedding 和 Rerank）

### 一键启动
双击 `start.bat` 即可自动启动前后端服务（自动检测端口冲突并清理）。

### 手动启动

```bash
# 后端（使用项目 .venv）
.venv\Scripts\python.exe run.py

# 前端
cd frontend
npm run dev
```

### 访问地址
- 前端：http://localhost:5173
- 后端 API：http://localhost:8002
- API 文档：http://localhost:8002/docs
- 健康检查：http://localhost:8002/api/health

## 项目结构

```
工单二/
├── api/
│   └── main.py                    # FastAPI 主程序（缓存、并行检索、耗时监控）
├── scripts/
│   ├── pipeline/
│   │   ├── chunker.py             # 分块器（表格保护 + 句子边界分块）
│   │   ├── bm25_retriever.py      # BM25 检索（jieba 分词）
│   │   ├── retriever.py           # 多路召回（RRF 融合 + 智能 Rerank）
│   │   ├── reranker.py            # BGE-Reranker 精排（GPU 加速）
│   │   ├── generator.py           # LLM 生成（5 条硬规则 + 重试）
│   │   ├── translator.py          # 翻译模块（双向翻译）
│   │   ├── query_understanding.py # Query 理解（意图识别 + 子查询扩展）
│   │   ├── embedder.py            # 向量编码（GPU / CUDA）
│   │   └── vector_store.py        # Milvus 向量存储
│   ├── middleware/
│   │   └── rate_limiter.py        # 请求限流中间件
│   ├── engine/
│   │   ├── mineru_engine.py       # MinerU 解析引擎
│   │   └── paddleocr_engine.py    # PaddleOCR 解析引擎
│   └── memory/
│       ├── chat_store.py          # 对话持久化（SQLite）
│       └── session_memory.py      # 会话记忆
├── frontend/
│   └── src/
│       ├── App.tsx                # 主组件（语言检测、翻译逻辑）
│       ├── api.ts                 # API 封装（含翻译、自检）
│       └── components/
│           ├── ChatArea.tsx       # 聊天区（翻译按钮、对比按钮）
│           └── InputBox.tsx       # 输入框
├── tests/                         # 测试代码
├── data/                          # 数据目录
├── storage/                       # 状态文件
├── logs/                          # 运行日志
├── .env                           # 环境配置（不进 git）
├── .env.example                   # 配置模板
├── run.py                         # 后端启动脚本（自动端口清理）
└── start.bat                      # 一键启动脚本
```

## 检索流程

```
用户问题 → 简单判断 → 是 → 跳过 Query 理解（省 2-3s）
                   → 否 → Query 理解（意图识别 + 子查询扩展）
    → 语义检索（Milvus 向量，GPU Embedding）  ──┐
    → BM25 检索（jieba 分词）                  ──┤→ RRF 融合 → 元数据过滤 → 智能 Rerank（GPU）→ Top-K
```

### 性能优化策略
- **查询缓存**：相同问题不重复调用 API，缓存命中 0.01s
- **简单问题跳过**：≤20 字符或含"是什么/谁是/what is"等模式的问题跳过 Query Understanding
- **并行执行**：Query 理解与 Embedding 并行，多个子查询并行检索
- **GPU 加速**：Embedding 和 Rerank 均在 GPU 上运行
- **智能 Rerank**：top-1 双路命中时跳过 Rerank

## 系统稳定性

### 容错机制
- **输入校验**：问题长度 ≤ 500 字、top_k 范围 1-20、语言只支持 zh/en
- **LLM 重试**：失败最多重试 2 次，间隔 0.5s/1s
- **LLM 超时**：单次调用 15s 超时
- **统一异常处理**：400（输入错误）、429（限流）、504（超时）、500（内部错误）
- **端口自动清理**：启动时检测 8002 端口占用并自动释放

### 资源管理
- **请求限流**：写操作每 IP 每秒最多 10 次，读操作不限
- **健康检查**：`GET /api/health` 检测系统状态
- **启动预热**：后台线程预加载所有模型（Embedding + Reranker + Query 理解）

## API 接口

### 问答
```bash
POST /api/query
{"question": "公司公开发行多少万股？", "top_k": 5, "language": "zh"}

POST /api/query/stream
{"question": "...", "language": "zh"}  # SSE 流式返回
```

### 翻译
```bash
POST /api/translate
{"text": "你好", "target_lang": "en"}
```

### 健康检查
```bash
GET /api/health
# {"status": "ok", "checks": {"initialized": true, "milvus": "ok"}}
```

## 配置说明

```env
# DeepSeek LLM
MIMO_API_KEY=your_api_key
MIMO_BASE_URL=https://api.deepseek.com/v1
MIMO_MODEL=deepseek-chat

# Embedding 模型（GPU）
EMBEDDING_MODEL_PATH=E:\AI_models\BGE-M3

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION=rag_workorder1

# Rerank（GPU 加速，已开启）
RERANK_ENABLED=true
RERANK_MODEL_PATH=E:\AI_models\bge-reranker-base

# 服务端口
API_HOST=0.0.0.0
API_PORT=8002
```

## 验收标准

| 指标 | 要求 | 实际 |
|------|------|------|
| 准确率 | ≥ 90% | 90.0%（10/10） |
| 首 token 响应 | ≤ 3s | ~3s（专业问题）/ ~1s（问候语） |
| 缓存命中 | - | 0.01s |
| 高可用性 | 稳定运行 | 健康检查 + 限流 + 重试 + 端口自动清理 |
| 容错机制 | 异常不崩溃 | 输入校验 + 统一异常处理 |