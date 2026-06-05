"""数据模型定义 - 所有 Pydantic 模型集中管理

集中管理所有数据模型的好处:
1. 类型安全: Pydantic v2 自动校验字段类型和取值范围
2. 序列化统一: 所有模型都支持 model_dump() 转 dict/JSON
3. 修改一处: 改变字段定义，所有使用方自动生效
"""

from __future__ import annotations
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class PageEngineType(str, Enum):
    """可用解析引擎类型枚举。字符串枚举可直接序列化为 JSON。"""
    MINERU = "mineru"
    PADDLE_OCR = "paddleocr"
    FALLBACK = "fallback"


class PageCategoryType(str, Enum):
    """页面分类类型枚举，决定使用哪个引擎组合来处理页面。"""
    NORMAL_TEXT = "normal_text"          # 正常文字页：仅用基础 OCR
    SEAL_STAMP = "seal_stamp"            # 印章页：PaddleOCR 增强
    FINANCIAL_TABLE = "financial_table"   # 财务报表页：MinerU 处理
    FORMULA_HEAVY = "formula_heavy"       # 公式密集页：MinerU 处理
    MULTI_COLUMN = "multi_column"         # 多栏布局页：MinerU 处理
    SCANNED_IMAGE = "scanned_image"       # 纯扫描图片页：PaddleOCR 识别


class PageProcessStatus(str, Enum):
    """页面处理状态枚举，用于断点续传的状态机。
    状态流转: PENDING -> ENHANCED (成功) / FAILED (失败)
    """
    PENDING = "pending"      # 待处理（初始状态）
    ENHANCED = "enhanced"    # 增强引擎处理完成
    FAILED = "failed"        # 处理失败
    SKIPPED = "skipped"      # 跳过（用户配置禁用）


class PageClassificationResult(BaseModel):
    """单页分类结果。由 PageJudge 产出，决定使用哪个引擎。"""
    page_no: int = Field(..., description="页码（从 1 开始）")
    category: PageCategoryType = Field(default=PageCategoryType.NORMAL_TEXT, description="页面分类")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度 0~1")
    has_seal_region: bool = Field(default=False, description="是否检测到红色印章")
    has_dense_table: bool = Field(default=False, description="是否密集表格(>=3)")
    has_formula: bool = Field(default=False, description="是否包含公式")
    is_multicolumn: bool = Field(default=False, description="是否多栏布局")
    label_counts: Dict[str, int] = Field(default_factory=dict, description="标签统计")

    def needs_paddleocr(self) -> bool:
        """是否需要 PaddleOCR 增强？"""
        return self.category in (PageCategoryType.SEAL_STAMP, PageCategoryType.SCANNED_IMAGE)

    def needs_mineru(self) -> bool:
        """是否需要 MinerU 增强？"""
        return self.category in (PageCategoryType.FINANCIAL_TABLE, PageCategoryType.FORMULA_HEAVY)


class PageProcessState(BaseModel):
    """单页处理状态，用于断点续传。"""
    page_no: int = Field(..., description="页码")
    status: PageProcessStatus = Field(default=PageProcessStatus.PENDING, description="处理状态")
    engines_used: List[str] = Field(default_factory=list, description="已使用引擎")
    error: Optional[str] = Field(default=None, description="错误信息")
    retry_count: int = Field(default=0, description="重试次数")


class BatchState(BaseModel):
    """批次处理状态快照，持久化到 storage/*_status.json 文件。"""
    pdf_name: str = Field(..., description="PDF 文件名")
    total_pages: int = Field(..., description="总页数")
    batch_size: int = Field(default=50, description="每批页数")
    pages: Dict[int, PageProcessState] = Field(default_factory=dict, description="各页状态")
    completed_batches: List[int] = Field(default_factory=list, description="已完成批次")
    current_batch: int = Field(default=0, description="当前批次")

    def get_pending_pages(self) -> List[int]:
        """获取待处理的页码列表。"""
        return [pn for pn, s in self.pages.items() if s.status == PageProcessStatus.PENDING]


class PageContent(BaseModel):
    """单页解析结果，最后合并为最终 Markdown。"""
    page_no: int = Field(..., description="页码")
    category: PageCategoryType = Field(..., description="页面分类")
    engines_used: List[str] = Field(..., description="使用的引擎")
    markdown: str = Field(default="", description="Markdown 内容")
    metadata: Dict[str, str] = Field(default_factory=dict, description="元数据")


class IngestReport(BaseModel):
    """文档解析最终报告。"""
    source_pdf: str = Field(..., description="源 PDF 路径")
    total_pages: int = Field(..., description="总页数")
    successful_pages: int = Field(..., description="成功页数")
    failed_pages: int = Field(..., description="失败页数")
    output_path: str = Field(..., description="输出文件路径")
    processing_time_seconds: float = Field(..., description="处理耗时（秒）")
    engines_used: List[str] = Field(..., description="使用的引擎")
    errors: List[str] = Field(default_factory=list, description="错误列表")