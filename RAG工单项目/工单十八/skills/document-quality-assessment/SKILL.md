---
name: document-quality-assessment
description: Document quality assessment skill。用于知识库入库前的文档质检，支持格式统计、PDF 类型识别、去重、敏感信息检测、OCR 路由建议和 HTML 报告输出。
---

# Document Quality Assessment Skill

这个 skill 的目标很简单：  
对一批文档先做“入库前质检”，再给出结构化报告和解析建议。

## 这个 skill 会做什么

1. 统计文档格式分布
2. 识别 PDF 是 `text_pdf`、`scan_pdf` 还是 `mixed_pdf`
3. 统计长度分布和异常短文档
4. 做 MD5 精确去重
5. 输出 SimHash 近似重复候选
6. 检测手机号、邮箱、身份证等敏感信息
7. 对扫描型和混合型 PDF 给出 OCR 路由结果，默认只做路由建议
8. 生成 JSON 报告和 HTML 报告

## 适用场景

- RAG 入库前先筛一遍文档质量
- 批量文档预处理前先看哪些要人工确认
- 想知道哪些 PDF 应该走 OCR，哪些可以直接走文本解析

## 最小执行入口

这个 skill 的实际执行代码在：

- `src/agents/skills/document_quality_assessment.py`
- `src/pipeline/quality_assessment_service.py`

如果你只是要“用这个 skill”，核心入口就是 `DocumentQualityAssessmentSkill.run(...)`。

## 相关资源

- 报告结构说明：`references/report-schema.md`
- 标签规则说明：`references/tagging-rules.md`
