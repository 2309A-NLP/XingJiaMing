# RAG 问答系统 - 工单3

**工单编号**：人工智能 NLP-RAG-基于 PDF 文档的问答系统

## 项目简介

基于大语言模型（LLM）的 RAG 问答系统，支持**多文档共存**，重点提升**检索准确率**、**响应速度**和**系统稳定性**。

### 核心能力

| 能力 | 说明 |
|------|------|
| 多文档共存 | 支持同时加载多份 PDF，查询时自动区分来源 |
| 双路召回 | 向量检索（BGE-M3）+ BM25（jieba 分词），RRF 融合排序 |
| 来源标注 | 回答中标注信息来自哪份文档 |
| 流式输出 | SSE 流式返回，首 token < 1 秒 |
| 查询缓存 | 相同问题直接返回缓存结果（TTL 300s） |
| 自动端口清理 | 启动时自动检测并清理占用端口的旧进程 |

### 技术栈

- **后端**：FastAPI + Python 3.10
- **前端**：React + TypeScript + Vite
- **向量数据库**：Milvus（Docker）
- **Embedding**：BGE-M3（GPU / CUDA，1024 维）
- **LLM**：DeepSeek-Chat（API）
- **PDF 解析**：MinerU + PaddleOCR
- **中文分词**：jieba

## 快速开始

### 环境要求
- Python 3.10+（项目自带 `.venv`）
- Node.js 18+
- Milvus（localhost:19530）
- NVIDIA GPU（CUDA，用于 Embedding）

### 一键启动
双击 `start.bat` 即可自动启动前后端服务。

### 手动启动
```bash
# 后端
.venv\Scripts\python.exe run.py

# 前端
cd frontend
npm run dev
```

### 访问地址
- 前端：http://localhost:5173
- 后端 API：http://localhost:8003
- API 文档：http://localhost:8003/docs

## 项目结构

```
工单三/
├── api/
│   ├── main.py                # FastAPI 入口（CORS、限流、异常处理、预加载）
│   ├── components.py          # 组件初始化（懒加载、多文档加载、分块缓存）
│   ├── routes/
│   │   ├── query.py           # 问答路由（双路召回、RRF 融合、流式输出）
│   │   ├── ingest.py          # 文档上传路由（追加模式，不清除旧数据）
│   │   ├── chat.py            # 对话管理路由
│   │   ├── health.py          # 健康检查路由
│   │   └── translate.py       # 翻译路由
│   ├── models.py              # Pydantic 数据模型
│   ├── cache.py               # 查询缓存（TTL 300s，最多 200 条）
│   └── progress.py            # 文档解析进度
├── scripts/
│   ├── pipeline/
│   │   ├── chunker.py         # 分块器（表格保护、句子边界、文档前缀 ID）
│   │   ├── embedder.py        # 向量编码（GPU/CUDA）
│   │   ├── vector_store.py    # Milvus 存储（多文档去重、source_file 过滤）
│   │   ├── bm25_retriever.py  # BM25 检索（jieba 分词）
│   │   ├── retriever.py       # 多路召回（RRF 融合，BM25 权重 1.5x）
│   │   ├── generator.py       # LLM 生成（多文档 prompt、来源标注）
│   │   ├── query_understanding.py  # Query 理解（备用，当前跳过）
│   │   ├── reranker.py        # Rerank 精排（备用，当前跳过）
│   │   └── ...
│   ├── engine/                # 文档解析引擎（MinerU、PaddleOCR）
│   ├── memory/                # 对话存储（SQLite）
│   └── middleware/            # 限流中间件
├── frontend/src/
│   ├── App.tsx                # 主组件
│   ├── api.ts                 # API 封装
│   └── components/
│       ├── ChatArea.tsx       # 聊天区（Markdown 渲染、来源展示）
│       └── InputBox.tsx       # 输入框
├── data/                      # PDF 和解析后的 MD（不进 git）
├── storage/                   # 对话数据库、分块缓存（不进 git）
├── logs/                      # 运行日志（不进 git）
├── docs/                      # 项目文档
├── .env                       # 环境配置（不进 git）
├── .env.example               # 配置模板
├── run.py                     # 启动脚本（端口自动清理）
└── start.bat                  # 一键启动
```

## 检索流程

```
用户问题
  ↓
问候语判断 → 是 → 直接返回（<0.1s）
  ↓ 否
Embedding 编码（GPU，~0.5s）
  ↓
┌─────────────────┬─────────────────┐
│ 向量检索（Milvus）│ BM25 检索（jieba）│
└────────┬────────┴────────┬────────┘
         ↓                 ↓
      RRF 融合（BM25 权重 1.5x）
         ↓
      Top-K 结果（含 source_file）
         ↓
      LLM 生成（带来源标注，~2s）
         ↓
      流式返回
```

## 多文档支持

### 文档入库
- 上传 PDF → 解析为 `_refined.md` → 分块（带文档前缀 ID）→ 编码 → 存入 Milvus
- 每个 chunk_id 带文档哈希前缀（如 `a3b1_c0000`），避免多文档 ID 冲突
- 新文档追加到索引，不清除旧数据

### 分块缓存
- 分块结果缓存到 `storage/chunks_cache.pkl`
- 后续启动直接读缓存，跳过分块（省几秒）
- 上传新文档时自动更新缓存

### 查询时
- 检索结果带 `source_file` 字段
- LLM prompt 包含多文档规则：区分不同文档、标注来源
- 上下文格式：`【资料1·来源：招股说明书2】标题\n内容`

## 性能指标

| 指标 | 数值 |
|------|------|
| 问候语响应 | < 0.1s |
| 简单查询 | 2-3s |
| 复杂查询 | 3-6s（取决于 LLM API 负载） |
| 首 token 时间 | < 1s |
| 缓存命中 | ~0.01s |
| 向量维度 | 1024 |

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
MILVUS_COLLECTION=rag_workorder3

# Rerank（可选，当前跳过以提升速度）
RERANK_ENABLED=true
RERANK_MODEL_PATH=E:\AI_models\bge-reranker-base

# 服务端口
API_HOST=0.0.0.0
API_PORT=8003
```