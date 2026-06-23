from __future__ import annotations

from src.core.settings import get_settings
from src.models.report_models import HtmlReport, QualityInspectionReport


def render_html_report(report: QualityInspectionReport, include_html_content: bool) -> HtmlReport:
    """把结构化报告渲染成简洁 HTML。"""

    settings = get_settings()
    settings.report_output_dir.mkdir(parents=True, exist_ok=True)
    html_content = _build_html_content(report)
    html_path = settings.report_output_dir / "latest_quality_report.html"
    html_path.write_text(html_content, encoding="utf-8")
    return HtmlReport(
        html_path=str(html_path),
        html_content=html_content if include_html_content else None,
    )


def _build_html_content(report: QualityInspectionReport) -> str:
    """优先突出待确认、待审核和路由决策。"""

    pending_reviews = "".join(
        f"<li>{item['file_name']} | {item['match_type']} | {item['masked_value']}</li>"
        for item in report.pending_reviews
    ) or "<li>无</li>"

    pending_confirmations = "".join(
        f"<li>{item['file_name']} | {item['reason']}</li>"
        for item in report.pending_confirmations
    ) or "<li>无</li>"

    simhash_candidates = "".join(
        f"<li>{item.left_file} ↔ {item.right_file} | distance={item.distance} | similarity={item.similarity}</li>"
        for item in report.duplicate_summary.simhash_candidates
    ) or "<li>无</li>"

    routing_decisions = "".join(
        (
            f"<li>{file_name} | parser={decision.get('parser_type', '-')}"
            f" | mode={decision.get('execution_mode', '-')}"
            f" | status={decision.get('execution_status', '-')}"
            f"</li>"
        )
        for file_name, decision in report.summary.routing_decisions.items()
    ) or "<li>无</li>"

    error_items = "".join(
        f"<li>{item.get('file_name', '-')} | {item.get('type', '-')} | {item.get('message', '-')}</li>"
        for item in report.errors
    ) or "<li>无</li>"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Document Quality Report</title>
  <style>
    body {{ font-family: "Segoe UI", "Microsoft YaHei", sans-serif; margin: 32px; color: #1f2937; }}
    h1, h2 {{ color: #0f172a; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 24px; }}
    .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px 14px; }}
    ul {{ line-height: 1.7; }}
  </style>
</head>
<body>
  <h1>Document Quality Report</h1>
  <div class="summary">
    <div class="card">总文档数: {report.summary.total_documents}</div>
    <div class="card">精确重复组: {report.summary.exact_duplicate_groups}</div>
    <div class="card">近似重复候选: {report.summary.simhash_candidate_groups}</div>
    <div class="card">敏感文档数: {report.summary.sensitive_documents}</div>
    <div class="card">失败文档数: {report.summary.failed_documents}</div>
  </div>
  <h2>待确认列表</h2>
  <ul>{pending_confirmations}</ul>
  <h2>待审核列表</h2>
  <ul>{pending_reviews}</ul>
  <h2>解析路由决策</h2>
  <ul>{routing_decisions}</ul>
  <h2>SimHash 候选</h2>
  <ul>{simhash_candidates}</ul>
  <h2>错误列表</h2>
  <ul>{error_items}</ul>
</body>
</html>
"""
