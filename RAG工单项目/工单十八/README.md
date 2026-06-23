# 工单十八：文档质量评估 Skill

## 项目简介

本项目实现了一个面向 RAG 入库前质检的 `skill`，用于在文档进入知识库之前完成基础质量评估、标签生成、解析路由建议和报告输出。

项目核心定位是“文档质量评估 skill”，不是重型文档解析平台。默认模式下优先保证质检链路稳定，真实 OCR 作为可选增强能力接入。

## 核心能力

- 支持 `pdf`、`docx`、`md`、`txt`
- 统计文档格式分布
- 识别 PDF 类型：`text_pdf`、`scan_pdf`、`mixed_pdf`
- 统计文本长度分布
- 支持 `MD5` 精确去重
- 支持 `SimHash` 近似重复候选提示
- 检测手机号、邮箱、身份证等敏感信息
- 生成文档标签、待确认列表、待审核列表
- 输出结构化 JSON 报告和 HTML 报告
- 支持同步、异步、任务恢复
- 支持 IMDR 小样本验证

## 项目结构

```text
工单十八/
├── config/                         # 配置文件
├── data/                           # 数据目录
├── logs/                           # 日志目录
├── scripts/                        # 验证脚本
├── skills/
│   └── document-quality-assessment/
├── src/
│   ├── agents/                     # Skill 调度与工作流
│   ├── api/                        # FastAPI 接口
│   ├── core/                       # 配置、日志、状态存储
│   ├── engine/                     # 文档抽取、OCR、解析路由
│   ├── memory/                     # 预留目录
│   ├── models/                     # Pydantic 模型
│   ├── pipeline/                   # 质检主流程
│   └── tools/                      # 预留目录
├── storage/
│   ├── ocr/                        # OCR 中间产物
│   ├── reports/                    # 报告产物
│   └── tasks/                      # 异步任务状态
├── tests/                          # 测试
├── tmp/                            # 临时验证目录
├── .env
├── .env.example
├── .gitignore
├── pytest.ini
├── README.md
├── requirements.txt
└── run.py
```

## Skill 入口

- Skill 元数据：`skills/document-quality-assessment/SKILL.md`
- Skill 执行入口：`src/agents/skills/document_quality_assessment.py`
- 主质检服务：`src/pipeline/quality_assessment_service.py`
- 顺序工作流：`src/agents/workflows/document_ingestion_workflow.py`

## 环境准备

### 1. 创建虚拟环境

```powershell
python -m venv .venv
```

### 2. 安装依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. 初始化环境变量

```powershell
Copy-Item .env.example .env
```

## 关键配置

以下配置建议优先确认：

- 服务配置：`APP_HOST`、`APP_PORT`
- 存储路径：`DATA_DIR`、`LOG_DIR`、`STORAGE_DIR`、`REPORT_OUTPUT_DIR`
- OCR 配置：`OCR_PROVIDER`、`OCR_EXECUTION_ENABLED`、`OCR_FAIL_ON_ERROR`、`OCR_COMMAND`
- PaddleOCR：`PADDLEOCR_EXECUTABLE`、`PADDLEOCR_LANG`
- MinerU：`MINERU_EXECUTABLE`、`MINERU_OUTPUT_DIR`
- 多模态配置：`MULTIMODAL_API_KEY`、`MULTIMODAL_BASE_URL`、`MULTIMODAL_MODEL`
- IMDR 验证：`IMDR_DOCUMENTS_DIR`、`IMDR_QUESTIONS_PATH`、`IMDR_VALIDATION_OUTPUT`

所有可变配置均通过环境变量管理，不在代码中硬编码。

## 启动方式

### 方式一：启动 API

```powershell
.\.venv\Scripts\python.exe run.py
```

或：

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.api.main:app --host 127.0.0.1 --port 8018 --reload
```

### 方式二：直接调用 Skill

```python
from src.agents.skills.document_quality_assessment import DocumentQualityAssessmentSkill
from src.models.api_models import QualityInspectionRequest

request = QualityInspectionRequest(
    file_paths=[r"E:\demo\sample.pdf"],
    mode="sync",
)

result = DocumentQualityAssessmentSkill().run(request)
print(result.model_dump())
```

## API 接口

### `POST /v1/document/quality-inspection`

发起文档质检任务。

请求体示例：

```json
{
  "folder_path": null,
  "file_paths": ["E:\\demo\\sample.pdf"],
  "mode": "sync",
  "include_html_content": true,
  "resume_existing": true,
  "config_overrides": null
}
```

约束：

- `folder_path` 和 `file_paths` 至少传一个
- `file_paths` 非空时优先使用 `file_paths`
- 只接受本机路径，不接受 URL

### `GET /v1/document/quality-inspection/{task_id}`

查询异步任务状态和报告结果。

### `POST /v1/document/quality-inspection/{task_id}/resume`

重跑失败任务。

## OCR 策略

默认行为：

- `scan_pdf` 和 `mixed_pdf` 只给出 OCR 路由建议
- 不强制执行真实 OCR

开启真实 OCR 后：

- 由 `OCR_PROVIDER` 决定使用 `auto`、`paddleocr`、`mineru` 或 `hybrid`
- 若依赖缺失或运行失败，会返回中文可读错误

建议在真实 OCR 验收时启用子进程模式：

```powershell
$env:OCR_COMMAND='subprocess'
```

## 报告结构

报告一级字段固定为：

- `summary`
- `format_distribution`
- `pdf_type_summary`
- `length_distribution`
- `duplicate_summary`
- `sensitive_info_summary`
- `document_labels`
- `pending_confirmations`
- `pending_reviews`
- `errors`
- `html_report`

其中：

- `routing_decisions` 位于 `summary`
- HTML 路径位于 `html_report.html_path`

## IMDR 验证

### 默认小样本验证

```powershell
.\.venv\Scripts\python.exe scripts\run_imdr_validation.py --folder "E:\桌面\新RAG工单\14-17附件\original_problems\documents" --questions "E:\桌面\新RAG工单\14-17附件\original_problems\questions.jsonl" --output ".\storage\reports\imdr_validation_report.json" --limit 5
```

### 开启真实 OCR 的小样本验证

```powershell
$env:OCR_COMMAND='subprocess'
.\.venv\Scripts\python.exe scripts\run_imdr_validation.py --folder "E:\桌面\新RAG工单\14-17附件\original_problems\documents" --questions "E:\桌面\新RAG工单\14-17附件\original_problems\questions.jsonl" --output ".\storage\reports\imdr_validation_report_ocr.json" --limit 5 --enable-ocr-execution
```

建议重点检查：

- `report.summary.routing_decisions`
- `report.pending_confirmations`
- `report.pending_reviews`
- `report.errors`

## 测试

运行全部测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

当前已覆盖：

- 分析器单测
- OCR 路由与错误降级
- API 同步、异步、恢复
- Skill Registry
- IMDR 验证脚本
- 端到端工作流

## 手动验收步骤

1. 创建 `.venv` 并安装依赖
2. 复制 `.env.example` 为 `.env`
3. 运行 `.\.venv\Scripts\python.exe -m pytest -q`
4. 启动 API
5. 调用同步接口验证 JSON 报告
6. 调用异步接口验证任务状态和恢复接口
7. 检查 `storage/tasks/`、`storage/reports/`、`storage/ocr/`
8. 运行 IMDR 小样本验证
9. 如需验真实 OCR，再增加 `--enable-ocr-execution`

## 已知限制

- 真实 OCR 仍依赖本机环境，不保证所有 Windows 机器零配置即跑
- 多模态能力目前是 OCR 辅助增强，不是主链路强依赖
- `resume` 当前更接近失败任务重跑，不是严格断点续跑
- `SimHash` 首版只做候选提示，不替代 `MD5` 精确去重
- IMDR 当前优先保证小样本跑通，完整题目级评测仍可继续扩展
