# RAG 问答系统 - 工单6

**工单编号**：人工智能 NLP-RAG-基于 PDF 文档的问答系统

## 项目简介

基于大语言模型（LLM）的 RAG 问答系统，支持**多文档共存**，重点提升**检索策略可配置性**和**检索质量评估**能力。

### 核心能力

| 能力 | 说明 |
|------|------|
| 多文档共存 | 支持同时加载多份 PDF，查询时自动区分来源 |
| 双路召回 | 向量检索（BGE-M3）+ BM25（jieba 分词），RRF 融合排序 |
| 检索策略配置 | 向量检索 / 全文检索 / 混合检索，支持前端实时切换 |
| 匹配模式 | 标准匹配 / 布尔查询(AND/OR/NOT) / 短语匹配 / 模糊匹配 / 自动检测 |
| 多种重排算法 | BGE / LLM / TF-IDF / 自适应，支持前端选择 |
| 多种嵌入模型 | 支持 BGE-M3、M3E 等模型切换 |
| 检索质量评估 | 准确率 / 召回率 / 响应时间，一键评估 |
| 来源标注 | 回答中标注信息来自哪份文档 |
| 流式输出 | SSE 流式返回，首 token < 1 秒 |
| 查询缓存 | 相同问题直接返回缓存结果（TTL 300s） |
| 多轮对话 | Redis 短期记忆，支持上下文追问 |
| 配置持久化 | 检索策略配置保存到 localStorage，刷新不丢失 |

### 技术栈

- **后端**：FastAPI + Python 3.10
- **前端**：React + TypeScript + Vite
- **向量数据库**：Milvus（Docker）
- **Embedding**：BGE-M3（GPU / CUDA，1024 维）、M3E
- **Reranker**：BGE-Reranker / LLM / TF-IDF / 自适应
- **LLM**：DeepSeek-Chat（API）
- **PDF 解析**：MinerU + PaddleOCR
- **中文分词**：jieba
- **短期记忆**：Redis（多轮对话上下文，最近 10 轮，TTL 1 小时）

## 快速开始

### 环境要求
- Python 3.10+（项目自带 `.venv`）
- Node.js 18+
- Milvus（localhost:19530）
- Redis（localhost:6379）
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
- 后端 API：http://localhost:8007
- API 文档：http://localhost:8007/docs

## 项目结构

```
工单六/
├── api/
│   ├── main.py                # FastAPI 入口
│   ├── init.py                # 组件初始化
│   ├── routes/
│   │   ├── query.py           # 问答路由（支持多种检索策略）
│   │   ├── chat.py            # 对话管理路由
│   │   ├── health.py          # 健康检查路由
│   │   ├── translate.py       # 翻译路由
│   │   ├── upload.py          # 文档上传路由
│   │   ├── embedding.py       # 嵌入模型管理路由
│   │   └── evaluate.py        # 检索质量评估路由
│   ├── models.py              # Pydantic 数据模型
│   ├── cache.py               # 查询缓存
│   └── progress.py            # 文档解析进度
├── scripts/
│   ├── pipeline/
│   │   ├── chunker.py         # 分块器
│   │   ├── embedder.py        # 向量编码（支持多模型切换）
│   │   ├── vector_store.py    # Milvus 存储
│   │   ├── bm25_retriever.py  # BM25 检索（支持布尔/短语/模糊匹配）
│   │   ├── retriever.py       # 多路召回（RRF 融合）
│   │   ├── reranker.py        # Rerank 精排（BGE/LLM/TF-IDF/自适应）
│   │   ├── rag_evaluator.py   # RAG 检索质量评估器
│   │   └── llm_generator.py   # LLM 生成
│   ├── engine/                # 文档解析引擎
│   ├── memory/
│   │   ├── chat_db.py         # 对话持久化（SQLite）
│   │   └── session_memory.py  # 多轮对话短期记忆（Redis）
│   └── middleware/            # 限流中间件
├── frontend/src/
│   ├── App.tsx                # 主组件
│   ├── api.ts                 # API 封装
│   └── components/
│       ├── ChatArea.tsx       # 聊天区（Markdown 渲染、来源展示、配置标签）
│       ├── InputBox.tsx       # 输入框
│       ├── Sidebar.tsx        # 侧边栏（三点菜单、评估按钮）
│       ├── SettingsModal.tsx  # 检索策略设置弹框
│       └── EvalModal.tsx      # 检索质量评估弹框
├── data/                      # PDF 和解析后的 MD
├── storage/                   # 对话数据库、分块缓存
├── logs/                      # 运行日志
├── docs/                      # 项目文档
├── .env                       # 环境配置
├── .env.example               # 配置模板
├── run.py                     # 启动脚本
└── start.bat                  # 一键启动
```

## 检索策略配置

### 支持的检索模式
- **向量检索**：通过语义相似度匹配，适合理解用户意图
- **全文检索**：基于 BM25 关键词匹配，适合精确查找特定术语
- **混合检索**：结合向量和全文检索，提供更全面的结果（默认）

### 匹配模式（全文检索/混合检索）
- **标准匹配**：基于 BM25 算法的关键词匹配
- **布尔查询**：支持 AND/OR/NOT 组合条件，如 `人工智能 AND 机器学习`
- **短语匹配**：引号内内容必须完整出现，如 `"招股说明书"`
- **模糊匹配**：容忍拼写错误，基于编辑距离匹配相似词
- **自动检测**：根据查询内容自动选择最合适的匹配模式

### 重排算法
- **BGE**：基于深度学习，准确率高，需要 GPU
- **LLM**：基于大语言模型，最准确但最慢
- **TF-IDF**：基于关键词相似度，速度最快
- **自适应**：根据查询长度自动选择最合适的算法

### 嵌入模型
- 支持 BGE-M3、M3E 等多种嵌入模型
- 模型列表从 `.env` 的 `EMBEDDING_MODELS` 配置读取
- 支持前端实时切换，已加载的模型自动缓存

## 检索质量评估

### 评估指标
- **准确率**：回答中包含预期关键词的比例（目标 ≥90%）
- **召回率**：相关文档被检索到的比例（目标 ≥95%）
- **响应时间**：从提问到返回答案的耗时（目标 <3s）

### 使用方式
1. 点击侧边栏底部的 📊 按钮
2. 选择要评估的检索策略（向量/全文/混合）
3. 点击「开始评估」
4. 查看评估结果：总评、三项核心指标、达标率、分类得分、逐题详情

### 测试问题集
内置 8 个标准测试问题，覆盖业务、风险、财务、结构、人力等类别。支持自定义测试问题集（JSON 格式）。

## 多轮对话

### 架构
- **短期记忆**：Redis 存储最近 10 轮对话，TTL 1 小时
- **持久化**：SQLite 存储完整对话记录（含检索配置）
- **上下文注入**：查询时从 Redis 读取历史，拼入 LLM messages

### 支持的场景
- 追问："那第二家呢？"
- 个人信息记忆："我叫李达" → "我是谁？" → "你是李达"
- 上下文补充："它的注册资本呢？"

## 性能指标

| 指标 | 数值 |
|------|------|
| 问候语响应 | < 0.1s |
| 简单查询 | 2-3s |
| 复杂查询 | 3-6s |
| 首 token 时间 | < 1s |
| 缓存命中 | ~0.01s |
| 向量维度 | 1024 |

## 配置说明

```env
# DeepSeek LLM
MIMO_API_KEY=your_api_key
MIMO_BASE_URL=https://api.deepseek.com/v1
MIMO_MODEL=deepseek-chat

# Embedding 模型（支持多模型）
EMBEDDING_MODEL_PATH=E:\AI_models\BGE-M3
EMBEDDING_MODELS=bge-m3:E:\AI_models\BGE-M3,m3e:E:\AI_models\model-m3e-base
DEFAULT_EMBEDDING_MODEL=bge-m3

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION=rag_workorder7

# Rerank
RERANK_ENABLED=true
RERANK_MODEL_PATH=E:\AI_models\bge-reranker-base

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# 服务端口
API_HOST=0.0.0.0
API_PORT=8007
```

## 工单6 新增功能

相比工单5，工单6新增以下功能：

1. **检索策略配置界面**：前端设置弹框，支持实时切换检索模式、匹配模式、重排算法、嵌入模型
2. **布尔查询**：支持 AND/OR/NOT 组合条件检索
3. **短语匹配**：引号内内容必须完整出现
4. **模糊匹配**：基于编辑距离的相似词匹配，容忍拼写错误
5. **多种嵌入模型支持**：支持 BGE-M3、M3E 等模型切换，已加载模型自动缓存
6. **多种重排算法**：BGE、LLM、TF-IDF、自适应四种算法可选
7. **检索质量评估**：一键评估准确率、召回率、响应时间，支持分类统计
8. **配置标签**：回答下方显示实际使用的检索模式、匹配模式、重排算法、嵌入模型
9. **配置持久化**：检索策略配置保存到 localStorage，刷新不丢失
10. **统一白色主题**：设置和评估弹框采用白色背景，文字清晰易读
