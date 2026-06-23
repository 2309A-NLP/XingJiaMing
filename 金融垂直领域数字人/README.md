# 金融垂直领域数字人

> 基于RAG的金融垂直领域数字人问答系统

## 项目概述

本项目实现了一个金融垂直领域的数字人问答系统，用户输入金融问题后，数字人能够：
1. 基于金融知识库（RAG）检索相关信息
2. 由LLM生成专业回答
3. 通过TTS将回答转为语音
4. 驱动数字人生成说话视频

## 系统架构

```
用户输入问题 → RAG检索 → LLM生成回答 → TTS语音合成 → 数字人视频生成
```

## 技术栈

| 模块 | 技术方案 |
|------|---------|
| RAG系统 | FastAPI + Milvus + BGE-M3 + DeepSeek-Chat |
| TTS语音 | Edge-TTS（zh-CN-YunyangNeural） |
| 数字人 | SadTalker + MuseTalk组合方案 |
| 部署平台 | AutoDL算力云（RTX 3090） |

## 效果视频

📁 `金融数字人_demo.mp4`

## 目录结构

```
金融垂直领域数字人/
├── 金融数字人_demo.mp4          # 最终效果视频
├── README.md                    # 项目说明
├── 项目文档.md                   # 详细文档
├── 设计/                         # 设计文档
│   ├── 系统架构设计.md
│   └── 技术选型分析.md
├── 研发/                         # 研发代码
│   ├── rag_client.py            # RAG客户端
│   └── rag_digital_human.py     # 主程序
├── 测试/                         # 测试文档
│   └── 测试方案.md
├── 优化/                         # 优化文档
│   ├── 口型优化方案.md
│   └── 文本清理方案.md
└── 部署/                         # 部署文档
    └── 部署指南.md
```

## 快速开始

### 1. 启动本地RAG

```powershell
cd E:\桌面\项目文件\RAG工单项目\工单六
$env:EMBEDDING_DEVICE="cpu"
.venv\Scripts\python.exe run.py
```

### 2. 启动ngrok

```powershell
ngrok http 8006
```

### 3. 启动数字人

SSH登录AutoDL后：
```bash
cd /root/autodl-tmp/Linly-Talker
python rag_digital_human.py
```

### 4. 访问WebUI

AutoDL控制台 → 自定义服务 → 6006端口

## 性能指标

| 指标 | 数值 |
|------|------|
| RAG响应时间 | 0.3-3秒 |
| TTS语音合成 | 2-3秒 |
| 视频生成时间 | 约540秒（9分钟） |
| 视频帧率 | 25fps |
| 视频分辨率 | 512x512 |

## 文档说明

- [项目文档.md](项目文档.md)：详细的项目文档
- [设计/系统架构设计.md](设计/系统架构设计.md)：系统架构设计
- [设计/技术选型分析.md](设计/技术选型分析.md)：技术选型分析
- [研发/rag_digital_human.py](研发/rag_digital_human.py)：主程序代码
- [测试/测试方案.md](测试/测试方案.md)：测试方案
- [优化/口型优化方案.md](优化/口型优化方案.md)：口型优化方案
- [优化/文本清理方案.md](优化/文本清理方案.md)：文本清理方案
- [部署/部署指南.md](部署/部署指南.md)：部署指南

## 版本信息

- 版本：v1.0
- 日期：2026-06-23
- 作者：Hermes
