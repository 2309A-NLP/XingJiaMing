# RAG 角色扮演系统

> 基于 RAG（检索增强生成）的多角色 AI 对话系统，支持刑事律师、心理医生、医疗门诊三种专业角色。

## 快速体验

**在线地址：** http://120.26.32.90

选择角色 → 输入问题 → AI 从知识库检索相关内容 → 按角色人设生成专业回复。

## 核心功能

- **三个专业角色**：刑事律师（林律）、心理医生（张心理）、医疗门诊（刘医学）
- **RAG 检索增强**：BGE-M3 嵌入 + Milvus 向量库 + BGE-Reranker 精排 + DeepSeek LLM
- **SSE 流式输出**：逐 token 返回回复
- **JWT 认证**：登录注册 + Token 鉴权
- **多级日志**：请求日志 + 错误专用日志 + JSON 结构化日志

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | HTML + Tailwind CSS + Vanilla JS (SPA) |
| 后端 | FastAPI + Uvicorn |
| 向量库 | Milvus 2.4.5 |
| 嵌入 | BGE-M3 (1024维) |
| 重排序 | BGE-Reranker |
| LLM | DeepSeek V4-Flash |
| 数据库 | MySQL + Redis |
| 部署 | Nginx + Docker Compose + systemd |

## 项目文档

- **[PROJECT_GUIDE.md](PROJECT_GUIDE.md)** — 10分钟代码讲解（架构、函数详解、测试数据、日志实现）
- **[DEPLOYMENT.md](DEPLOYMENT.md)** — 部署运维指南

## 目录结构

```
src/                     后端源码
├── fastapi_app.py       API 路由 + RAG 管线
├── config/settings.py   全局配置
├── db/mysql.py          MySQL 操作
├── db/redis.py          Redis 操作
├── rag/                 RAG 核心模块
│   ├── embedding.py     文本向量化
│   ├── retrieval.py     Milvus 检索
│   └── rerank.py        结果重排序
├── utils/logger.py      统一日志系统
└── templates/           前端页面

tests/                   测试
├── test_ragas.py        RAGAS 质量评估
└── ragas_results.json   15题评估数据
```

## RAGAS 评估结果

| 指标 | 评分 | 含义 |
|------|------|------|
| Faithfulness | 0.49 | 忠实度（需改进） |
| AnswerRelevancy | 0.83 | 回答相关性 ✅ |
| ContextPrecision | 1.00 | 检索精确度 ✅ |
| ContextRecall | 1.00 | 检索召回率 ✅ |
| **综合** | **0.83** | ✅ |
