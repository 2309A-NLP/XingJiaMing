# RAG 性能优化系统 - 工单十三

**工单编号**：人工智能 NLP-RAG-性能瓶颈识别与优化

## 项目简介

工单十三基于 `工单十二` 的 RAG 问答系统做独立优化交付，目标是把传统 RAG 主链路中的 `query -> 检索结果返回` 压到 `3s` 内，并沉淀完整的性能埋点、基准测试和优化对比材料。

当前版本重点优化传统 RAG 主链路：

- 新增 `POST /api/query/retrieve` 作为检索硬验收接口
- 为 `query / query/stream / query/compare` 增加 `trace_id`、`timings`、`retrieval_time_ms`、`total_time_ms`、`cache_hit`
- embedding 与 BM25 并行
- rerank 候选数限制为可配置上限
- 上下文长度与生成 token 上限收紧
- 启动时预热 embedding / reranker / generator

LightRAG 仍保留独立能力，但不纳入首版传统 RAG 时延口径。

## 技术栈

- 后端：FastAPI + Python 3.10
- 前端：React + TypeScript + Vite
- 向量数据库：Milvus
- 图检索：LightRAG + Neo4j
- Embedding：BGE-M3 / M3E
- Reranker：BGE-Reranker / TF-IDF / Adaptive
- LLM：DeepSeek-Chat
- 会话记忆：Redis

## 目录说明

```text
工单十三/
├── api/                  # FastAPI 路由与初始化
├── scripts/              # 数据处理、评估与性能脚本
├── frontend/             # React 前端
├── tests/                # 本次补充的接口/优化测试
├── docs/                 # 优化报告、截图与对比结果
├── data/                 # 文档数据
└── .env.example          # 工单十三独立配置模板
```

## 快速开始

1. 复制配置模板：

```bash
copy .env.example .env
```

2. 确认基础依赖可用：

- Milvus: `127.0.0.1:19530`
- Redis: `127.0.0.1:6379`
- Neo4j: `127.0.0.1:7687`（仅 LightRAG 需要）
- Embedding 模型路径和 Reranker 模型路径存在

3. 启动后端：

```bash
python run.py
```

4. 启动前端：

```bash
cd frontend
npm install
npm run dev
```

默认地址：

- 前端：`http://localhost:5173`
- 后端：`http://localhost:8013`
- OpenAPI：`http://localhost:8013/docs`

## 关键接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/query/retrieve` | POST | 只做检索，返回性能分解，作为 3 秒验收主接口 |
| `/api/query` | POST | 完整问答，返回性能字段 |
| `/api/query/stream` | POST | 流式问答，`done` 事件中携带性能字段 |
| `/api/query/compare` | POST | 传统 RAG vs 纯 LLM 对比 |
| `/api/evaluate` | POST | 输出平均值、P50/P95/P99、3 秒达标率 |

## 性能脚本

- `python scripts/perf_breakdown.py`
  作用：单请求阶段耗时拆解

- `python scripts/perf_benchmark.py`
  作用：固定问题集稳态基准，输出 `benchmark_results.json`

- `python scripts/perf_load_smoke.py`
  作用：轻量并发压测骨架，输出 `load_smoke_results.json`

## 测试

当前已补的自动化测试：

```bash
python tests\test_query_performance_api.py
python tests\test_pipeline_optimizations.py
```

覆盖点：

- `retrieve` 接口契约
- `query` 缓存命中与性能字段
- `stream` `done` 事件性能摘要
- `evaluate` 分位数字段
- rerank 候选截断
- 上下文长度裁剪

## 交付物

本工单目录内最终应包含：

- 优化后的完整代码
- 性能脚本与测试
- `docs/perf/` 中的基准结果
- 优化前后对比报告
- 过程问题记录与截图说明
