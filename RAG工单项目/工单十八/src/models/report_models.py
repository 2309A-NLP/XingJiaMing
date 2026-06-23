from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HtmlReport(BaseModel):
    """HTML 报告信息。"""

    html_path: str | None = None
    html_content: str | None = None


class DuplicateGroup(BaseModel):
    """完全重复文件分组。"""

    md5_hash: str
    files: list[str] = Field(default_factory=list)


class SimHashCandidate(BaseModel):
    """近似重复候选。"""

    files: list[str] = Field(default_factory=list)
    left_file: str
    right_file: str
    distance: int
    similarity: float


class DuplicateSummary(BaseModel):
    """重复检测汇总。"""

    exact_duplicate_groups: list[DuplicateGroup] = Field(default_factory=list)
    simhash_candidates: list[SimHashCandidate] = Field(default_factory=list)


class SensitiveInfoSummary(BaseModel):
    """敏感信息汇总。"""

    total_matches: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)


class ReportSummary(BaseModel):
    """报告顶部汇总。"""

    total_documents: int
    supported_documents: int
    unsupported_documents: int = 0
    exact_duplicate_groups: int = 0
    simhash_candidate_groups: int = 0
    sensitive_documents: int = 0
    failed_documents: int = 0
    routing_decisions: dict[str, dict[str, Any]] = Field(default_factory=dict)


class QualityInspectionReport(BaseModel):
    """完整质检报告。"""

    summary: ReportSummary
    format_distribution: dict[str, dict[str, Any]] = Field(default_factory=dict)
    pdf_type_summary: dict[str, dict[str, Any]] = Field(default_factory=dict)
    length_distribution: dict[str, Any] = Field(default_factory=dict)
    duplicate_summary: DuplicateSummary = Field(default_factory=DuplicateSummary)
    sensitive_info_summary: SensitiveInfoSummary = Field(default_factory=SensitiveInfoSummary)
    document_labels: dict[str, list[str]] = Field(default_factory=dict)
    pending_confirmations: list[dict[str, Any]] = Field(default_factory=list)
    pending_reviews: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    html_report: HtmlReport = Field(default_factory=HtmlReport)


class InspectionExecutionResult(BaseModel):
    """一次工作流执行结果。"""

    task_id: str | None = None
    status: str
    progress: int = 100
    report: QualityInspectionReport | None = None
    error_message: str | None = None
    current_step: str = "finish"
    completed_steps: list[str] = Field(default_factory=list)
