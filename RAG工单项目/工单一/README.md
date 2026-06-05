# RAG 问答系统 - 工单1

**工单编号**：人工智能 NLP-RAG-基于 PDF 文档的问答系统

## 项目简介

基于大语言模型（LLM）的问答系统，能够针对《招股说明书》中的内容进行高效的问答检索。

### 核心功能
- **Query 理解**：准确理解用户问题的意图，支持意图识别、消歧、分解和抽象
- **检索与生成**：结合 LLM 和检索技术，快速从招股说明书中提取相关信息并生成准确、简洁的回答
- **用户体验**：提供友好的交互界面，支持问题输入、答案展示和反馈机制

### 技术栈
- **后端**：FastAPI + Python
- **前端**：React + TypeScript + Vite
- **向量数据库**：Milvus
- **Embedding 模型**：BGE-M3
- **LLM**：DeepSeek-Chat

## 快速开始

### 环境要求
- Python 3.10+
- Node.js 18+
- Milvus Docker（已运行在 localhost:19530）

### 一键启动
双击 `start.bat` 即可启动前后端服务。

### 手动启动

#### 1. 启动后端
```bash
python run.py
```

#### 2. 启动前端
```bash
cd frontend
npm run dev
```

#### 3. 访问系统
- 前端：http://localhost:5173
- 后端 API：http://localhost:8000
- API 文档：http://localhost:8000/docs

## 项目结构

```
工单一/
├── .venv/                  # Python 虚拟环境（符号链接）
├── api/                    # 后端 API
│   ├── __init__.py
│   └── main.py            # FastAPI 主程序
├── data/                   # 数据目录（符号链接）
│   ├── 招股说明书1.pdf
│   └── 招股说明书1_refined.md
├── frontend/               # 前端代码
│   ├── node_modules/       # Node.js 依赖
│   ├── src/                # 源代码
│   ├── package.json
│   └── vite.config.ts
├── scripts/                # 核心脚本（符号链接）
│   ├── pipeline/           # RAG 管线
│   │   ├── query_understanding.py  # Query 理解模块
│   │   ├── chunker.py              # 文本分块
│   │   ├── embedder.py             # 向量编码
│   │   ├── vector_store.py         # 向量存储
│   │   ├── bm25_retriever.py       # BM25 检索
│   │   ├── retriever.py            # 多路召回检索器
│   │   ├── reranker.py             # 重排序
│   │   └── generator.py            # LLM 生成
│   ├── memory/             # 对话记忆
│   └── engine/             # 文档解析引擎
├── .env                    # 环境配置
├── run.py                  # 后端启动脚本
├── start.bat               # 一键启动脚本
└── README.md               # 项目说明
```

## Query 理解功能

### 功能说明
系统使用 LLM 对用户问题进行深度理解，包括：

1. **意图识别**：识别问题属于哪种类型
   - 事实性问题（factoid）
   - 比较性问题（comparison）
   - 总结性问题（summary）
   - 解释性问题（explanation）
   - 列举性问题（list）
   - 定义性问题（definition）
   - 时间性问题（temporal）
   - 数量性问题（quantitative）

2. **消歧**：处理多义词或模糊表述，确保问题的准确性

3. **分解与抽象**：将复杂问题分解为多个子问题，提取关键信息

### API 接口

#### 分析 Query
```bash
POST /query/analyze
{
  "question": "公司的核心竞争力是什么？"
}

# 返回
{
  "original_query": "公司的核心竞争力是什么？",
  "intent": "explanation",
  "intent_description": "解释性问题 - 要求解释原因或机制",
  "disambiguated_query": "公司的核心竞争力是什么？",
  "sub_queries": ["公司的核心竞争力是什么？"],
  "keywords": ["公司", "核心竞争力"],
  "confidence": 0.95
}
```

#### 流式问答（带 Query 分析）
```bash
POST /query/stream
{
  "question": "公司的核心竞争力是什么？",
  "top_k": 5
}

# 返回 SSE 流
data: {"type": "query_analysis", "data": {...}}
data: {"type": "sources", "data": [...]}
data: {"type": "token", "data": "..."}
...
data: {"type": "done"}
```

## 验收问题

工单要求使用以下 10 个问题进行验收测试：

1. 报告期内，武汉兴图新科电子股份有限公司来自军用领域的收入分别是多少？
2. 武汉兴图新科电子股份有限公司参与制定了哪个技术标准？
3. 报告期内，武汉兴图新科电子股份有限公司来自军用领域的收入占主营业务收入的比重分别是多少？
4. 根据武汉兴图新科电子股份有限公司招股意向书，电子信息行业的上游涉及哪些企业？
5. 武汉兴图新科电子股份有限公司在哪个领域已经成为重要供应商？
6. 根据武汉兴图新科电子股份有限公司招股意向书，电子信息行业的下游主要包括哪些行业？
7. 武汉兴图新科电子股份有限公司参与的哪个工程荣获了国家科技进步一等奖？
8. 武汉兴图新科电子股份有限公司注册资本是多少？
9. 武汉兴图新科电子股份有限公司法定代表人是谁？
10. 武汉兴图新科电子股份有限公司计划使用本次发行募集资金的多少用于补充流动资金？

## 验收标准

### 功能验收
1. **PDF 解析**：能够准确解析 PDF 文档中的文字、表格数据
2. **问答准确性**：问答系统能够基于 pdf 文档中的内容返回答案
3. **交互友好性**：提供清晰、简洁的用户界面
4. **多语言支持**：支持中文和英文的问答

### 性能验收
1. **响应时间**：从用户提问到返回答案的时间应不超过 3 秒
2. **资源消耗**：系统应合理利用计算资源，确保在高并发环境下稳定运行

## 配置说明

### 环境变量（.env）
```env
# DeepSeek LLM 配置
MIMO_API_KEY=your_api_key
MIMO_BASE_URL=https://api.deepseek.com/v1
MIMO_MODEL=deepseek-chat

# Embedding 模型配置
EMBEDDING_MODEL_PATH=E:\AI_models\BGE-M3

# Milvus 配置
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION=rag_workorder1

# 数据目录
DATA_DIR=./data

# Rerank 配置（可选）
RERANK_ENABLED=false
RERANK_MODEL_PATH=E:\AI_models\bge-reranker-base
```

## 常见问题

### 1. Milvus 连接失败
确保 Milvus Docker 已启动：
```bash
docker ps | grep milvus
```

### 2. 模型加载失败
检查 `EMBEDDING_MODEL_PATH` 路径是否正确，确保模型文件存在。

### 3. 前端启动失败
确保已安装 Node.js 依赖：
```bash
cd frontend
npm install
```

## 技术文档

详细的技术文档请参考：
- 系统架构：见本文档"项目结构"部分
- 技术选型：见本文档"技术栈"部分
- 开发流程：见本文档"快速开始"部分

## 用户手册

### 如何上传 PDF 文档
1. 点击界面上的"上传"按钮
2. 选择 PDF 文件
3. 等待解析完成

### 如何提问
1. 在输入框中输入问题
2. 点击"发送"按钮或按回车键
3. 等待 AI 回答

### 如何查看 Query 分析
1. AI 回答后，点击"🔍 Query 分析"按钮
2. 查看意图识别、消歧、分解结果

### 如何查看结果
1. AI 回答会显示在聊天区域
2. 点击"来源"按钮可查看引用的原文

## 许可证

内部项目，仅供学习使用。
