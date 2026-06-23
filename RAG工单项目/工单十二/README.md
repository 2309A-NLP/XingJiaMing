# RAG 问答系统 - 工单12（LightRAG 优化）

**工单编号**：人工智能 NLP-RAG-基于 PDF 文档的问答系统

## 项目简介

在现有 RAG 系统基础上，引入 **LightRAG** 知识图谱检索，对比传统 RAG vs LightRAG 的检索效果，使用 RAGAS 评估指标进行量化对比。

### 核心对比

| 维度 | 传统 RAG | LightRAG |
|------|----------|----------|
| 检索方式 | 向量检索 + BM25 + RRF 融合 | 知识图谱 + 向量 + 混合检索 |
| 索引结构 | 文档分块 → Embedding → Milvus | 实体/关系抽取 → Neo4j 图谱 |
| 上下文理解 | 基于语义相似度 | 基于实体关系网络 |
| 优势 | 简单高效、通用性强 | 结构化推理、跨文档关联 |

### 技术栈

- **后端**：FastAPI + Python 3.10
- **前端**：React + TypeScript + Vite
- **向量数据库**：Milvus（Docker）
- **图数据库**：Neo4j（Docker）
- **Embedding**：BGE-M3（1024 维）
- **Reranker**：BGE-Reranker
- **LLM**：DeepSeek-Chat（API）
- **LightRAG**：HKUDS/LightRAG
- **短期记忆**：Redis（多轮对话）

### 数据源

- 《招股说明书1》武汉力源信息技术股份有限公司
- 《招股说明书2》武汉兴图新科电子股份有限公司

## 快速开始

### 环境要求
- Python 3.10+（项目自带 `.venv`）
- Node.js 18+
- Milvus（localhost:19530）
- Neo4j（localhost:7474 / 7687）
- Redis（localhost:6379）
- NVIDIA GPU（CUDA，用于 Embedding）

### 启动步骤

```bash
# 1. 启动 Docker 容器（Milvus + Neo4j + Redis）
# 确保 Docker Desktop 已启动，容器在 Windows 本地运行

# 2. 后端
.venv\Scripts\python.exe run.py
# 或
cd /mnt/e/桌面/项目文件/RAG工单项目/工单十二
NO_PROXY='*' no_proxy='*' PYTHONUTF8=1 .venv/Scripts/python.exe run.py

# 3. 前端
cd frontend
npm run dev
```

### 访问地址
- 前端：http://localhost:5173
- 后端 API：http://localhost:8012
- API 文档：http://localhost:8012/docs
- Neo4j 浏览器：http://localhost:7474

## 功能说明

### 1. 知识图谱构建
```bash
# 通过 API 触发文档入库
POST /api/lightrag/insert
{
  "file_patterns": ["*_refined.md"]
}
```

### 2. RAG vs LightRAG 对比查询
前端点击 🔍 按钮，输入问题即可同时查询两种方式并对比结果。

### 3. RAGAS 评估
运行评估脚本生成量化对比报告：
```bash
.venv\Scripts\python.exe scripts/eval_lightrag.py
```

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/lightrag/insert` | POST | 将文档插入知识图谱 |
| `/api/lightrag/query` | POST | LightRAG 查询 |
| `/api/lightrag/compare` | POST | RAG vs LightRAG 对比 |
| `/api/lightrag/status` | GET | 知识图谱状态 |
| `/api/query/stream` | POST | 传统 RAG 流式查询 |
| `/api/health` | GET | 健康检查 |

## 项目结构

```
工单十二/
├── api/
│   ├── main.py                # FastAPI 入口
│   ├── init.py                # 组件初始化
│   └── routes/
│       ├── query.py           # 传统 RAG 查询
│       ├── lightrag.py        # LightRAG 接口（新增）
│       ├── chat.py            # 对话管理
│       └── ...
├── scripts/
│   ├── pipeline/
│   │   ├── lightrag_service.py  # LightRAG 服务封装（新增）
│   │   ├── vector_store.py      # Milvus 向量存储
│   │   └── ...
│   └── eval_lightrag.py         # RAGAS 评估脚本（新增）
├── frontend/src/
│   └── components/
│       └── CompareModal.tsx     # 对比展示弹框（新增）
├── data/                        # 招股说明书 PDF + 解析 MD
├── lightrag_storage/            # LightRAG 知识图谱存储
├── run_insert.py                # 独立入库脚本（新增）
└── .env
```
