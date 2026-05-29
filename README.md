# 多角色智能问答系统 - RAG RolePlay System

基于 RAG（检索增强生成）架构的多角色 AI 对话系统，支持刑事律师、心理医生、医疗门诊三种专业角色。

## 📁 项目结构

```
├── 研发/                    # 源代码
│   └── rag-roleplay-system/
│       ├── src/             # 核心源码 (FastAPI + RAG管线)
│       ├── scripts/         # 数据初始化脚本
│       ├── tests/           # 测试用例 (20+)
│       ├── data/            # PDF知识库 & 对话模版
│       ├── nginx/           # Nginx配置
│       └── docs/            # 项目文档
├── 设计/                    # 架构设计 & 思维导图
├── 优化/                    # 优化方案 (架构/性能/安全/RAG质量)
├── 部署/                    # 阿里云部署脚本 (一键部署)
└── 测试/                    # 测试文档
```

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 向量数据库 | Milvus 2.4.5 (Docker) |
| 关系数据库 | MySQL |
| 缓存 | Redis |
| 嵌入模型 | BGE-M3 (1024维) |
| 重排序 | BGE-Reranker-Base |
| LLM | DeepSeek V4-Flash API |
| 反向代理 | Nginx |
| 认证 | JWT + bcrypt |

## 🚀 快速部署

```bash
cd 部署/
sudo bash deploy_all.sh --domain your-domain.com --email your@email.com
```

## 📊 RAGAS 评估

| 指标 | 评分 |
|------|------|
| Faithfulness | 0.49 |
| Answer Relevancy | 0.83 |
| Context Precision | 1.00 |
| Context Recall | 1.00 |
| **综合** | **0.83** |

## 📄 License

MIT License
