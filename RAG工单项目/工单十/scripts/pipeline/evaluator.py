"""解析质量评估器 (ParseEvaluator)

对 MinerU + PaddleOCR 文档解析管道的输出进行质量评估打分。

评估维度:
  1. 文本保真度 (Fidelity): 解析文本与原文的字符级匹配度
  2. 内容完整性 (Completeness): 解析出的内容是否覆盖原文
  3. 噪声率 (Noise Rate): 页眉/页脚/异常字符占比
  4. 结构保留度 (Structure): 段落/换行/分段符保留情况
  5. 压缩比 (Compression): 解析后的有效内容占比

评分: 每项 0-100 分，综合为加权平均分。
不需要外部依赖，纯 Python 实现。
"""

from __future__ import annotations
import difflib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class EvalReport:
    """评估报告。"""
    pdf_name: str                              # 原 PDF 文件名
    total_pages: int = 0                       # 总页数
    parsed_pages: int = 0                      # 成功解析页数
    raw_chars: int = 0                         # 原文总字符数
    parsed_chars: int = 0                      # 解析后字符数
    valid_chars: int = 0                       # 解析后有效字符数（去噪后）

    # 评分 (0-100)
    fidelity_score: float = 0.0                # 文本保真度评分
    completeness_score: float = 0.0            # 内容完整性评分
    noise_score: float = 0.0                   # 噪声控制评分
    structure_score: float = 0.0               # 结构保留评分
    overall_score: float = 0.0                 # 综合评分

    # 详细统计
    matched_chars: int = 0                     # 匹配字符数
    missing_chars: int = 0                     # 丢失字符数
    extra_chars: int = 0                       # 多余字符数
    noise_lines: int = 0                       # 噪声行数
    short_line_count: int = 0                  # 短行（≤2字）数量

    # 噪声明细
    header_footer_patterns: Dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        """生成可读的摘要报告。"""
        lines = [
            f"╔{'═'*50}╗",
            f"║  解析质量评估报告",
            f"╠{'═'*50}╣",
            f"║  文件: {self.pdf_name}",
            f"║  页数: {self.parsed_pages}/{self.total_pages}",
            f"║  原文: {self.raw_chars:,} 字符 → 解析: {self.parsed_chars:,} 字符",
            f"║",
            f"║  📊 评分明细:",
            f"║     文本保真度:    {self.fidelity_score:>5.1f} / 100",
            f"║     内容完整性:    {self.completeness_score:>5.1f} / 100",
            f"║     噪声控制:      {self.noise_score:>5.1f} / 100",
            f"║     结构保留:      {self.structure_score:>5.1f} / 100",
            f"║",
            f"║  ⭐ 综合评分:     {self.overall_score:>5.1f} / 100",
            f"╚{'═'*50}╝",
        ]
        return "\n".join(lines)

    def detailed(self) -> str:
        """生成详细的评估报告。"""
        report = self.summary()
        details = [
            f"\n{'─'*50}",
            f"  详细统计:",
            f"    匹配字符:   {self.matched_chars:,}",
            f"    丢失字符:   {self.missing_chars:,}",
            f"    多余字符:   {self.extra_chars:,}",
            f"    噪声行数:   {self.noise_lines:,}",
            f"    短行数量:   {self.short_line_count:,}",
        ]
        if self.header_footer_patterns:
            details.append(f"\n  检测到的页眉/页脚模式:")
            for pattern, count in sorted(
                self.header_footer_patterns.items(),
                key=lambda x: -x[1]
            )[:10]:
                details.append(f"    [{count}次] {pattern[:50]}")
        report += "\n".join(details)
        return report


class ParseEvaluator:
    """文档解析质量评估器。

    基于原文（PDF 直接提取文本）和解析后文本的对比，
    从多维度评估解析质量。
    """

    # 页眉/页脚模式（用于检测噪声）
    HEADER_FOOTER_PATTERNS: List[re.Pattern] = [
        re.compile(r"^.*\u62db\u80a1\u610f\u5411\u4e66$"),           # "XXX 招股意向书"
        re.compile(r"^\d+-\d+-\d+$"),                                  # "1-1-0"
        re.compile(r"^\d{1,4}$"),                                      # 纯数字页码
        re.compile(r"^\u4fdd\u8350\u673a\u6784"),                     # "保荐机构"
        re.compile(r"^\u58f0\s*\u660e$"),                              # "声 明"
    ]

    def __init__(self):
        pass

    def evaluate_from_files(
        self,
        pdf_path: str | Path,
        parsed_md_path: str | Path,
        sample_pages: Optional[int] = None,
    ) -> EvalReport:
        """从文件评估解析质量。

        Args:
            pdf_path: 原始 PDF 文件路径。
            parsed_md_path: 解析后的 Markdown 文件路径。
            sample_pages: 抽样页数（None=全部）。

        Returns:
            评估报告。
        """
        pdf_path = Path(pdf_path)
        parsed_md_path = Path(parsed_md_path)

        # 读取解析后的 Markdown
        parsed_text = parsed_md_path.read_text(encoding="utf-8")

        # 提取原文（通过 PyMuPDF）
        raw_text = self._extract_raw_text(pdf_path)

        # 提取页面信息
        total_pages = self._count_pdf_pages(pdf_path)

        # 执行评估
        report = self._evaluate(
            raw_text, parsed_text, pdf_path.stem, total_pages
        )

        return report

    def evaluate_from_texts(
        self,
        raw_text: str,
        parsed_text: str,
        pdf_name: str = "unknown",
        total_pages: int = 0,
    ) -> EvalReport:
        """直接从文本评估解析质量。

        Args:
            raw_text: 原始 PDF 提取的文本。
            parsed_text: 解析后的 Markdown 文本。
            pdf_name: PDF 文件名。
            total_pages: 总页数。

        Returns:
            评估报告。
        """
        return self._evaluate(raw_text, parsed_text, pdf_name, total_pages)

    # ──────────────────────────────────────────────
    # 内部方法
    # ──────────────────────────────────────────────

    def _evaluate(
        self,
        raw_text: str,
        parsed_text: str,
        pdf_name: str,
        total_pages: int,
    ) -> EvalReport:
        """执行评估。"""
        report = EvalReport(pdf_name=pdf_name, total_pages=total_pages)

        # ---- 基础统计 ----
        report.raw_chars = len(raw_text)
        report.parsed_chars = len(parsed_text)

        # ---- 计算文本保真度 (Fidelity) ----
        # 使用 difflib 的 SequenceMatcher 计算字符级匹配
        matcher = difflib.SequenceMatcher(None, raw_text, parsed_text)
        report.matched_chars = int(matcher.ratio() * min(len(raw_text), len(parsed_text)))
        report.missing_chars = len(raw_text) - report.matched_chars
        report.extra_chars = len(parsed_text) - report.matched_chars

        # 保真度评分：基于匹配比例
        similarity = matcher.ratio()
        report.fidelity_score = min(100, round(similarity * 100, 1))

        # ---- 计算内容完整性 (Completeness) ----
        # 原文中的重要关键字是否都被解析出来了
        key_phrases = self._extract_key_phrases(raw_text)
        found = 0
        for phrase in key_phrases:
            if phrase in parsed_text:
                found += 1
        completeness_ratio = found / max(len(key_phrases), 1)
        report.completeness_score = min(100, round(completeness_ratio * 100, 1))

        # ---- 计算噪声控制 (Noise) ----
        parsed_lines = parsed_text.split("\n")
        noise_count = 0
        short_count = 0
        header_footer_stats: Dict[str, int] = {}

        for line in parsed_lines:
            stripped = line.strip()
            # 跳过注释行
            if stripped.startswith("<!--") and stripped.endswith("-->"):
                continue

            # 短行统计
            if stripped and len(stripped) <= 2:
                short_count += 1

            # 页眉/页脚检测
            for pattern in self.HEADER_FOOTER_PATTERNS:
                if pattern.match(stripped):
                    noise_count += 1
                    key = stripped[:40]
                    header_footer_stats[key] = header_footer_stats.get(key, 0) + 1
                    break

        report.short_line_count = short_count
        report.noise_lines = noise_count
        report.header_footer_patterns = header_footer_stats

        total_non_comment = sum(1 for l in parsed_lines
                                if l.strip() and not (l.strip().startswith("<!--")
                                                      and l.strip().endswith("-->")))
        noise_ratio = noise_count / max(total_non_comment, 1)
        report.noise_score = min(100, round((1 - noise_ratio) * 100, 1))

        # ---- 计算结构保留度 (Structure) ----
        # 检查分段符 --- 的保留率
        raw_separators = raw_text.count("\\f") + raw_text.count("\\n\\n")
        parsed_separators = parsed_text.count("---")
        # 分段符保留率
        expected_pages = max(total_pages - 1, 1)
        struct_ratio = min(parsed_separators / expected_pages, 1.0)
        report.structure_score = min(100, round(struct_ratio * 100, 1))

        # ---- 统计页面 ----
        report.parsed_pages = total_pages
        report.valid_chars = report.parsed_chars - noise_count * 20

        # ---- 综合评分 ----
        report.overall_score = round(
            report.fidelity_score * 0.35
            + report.completeness_score * 0.25
            + report.noise_score * 0.25
            + report.structure_score * 0.15,
            1,
        )

        return report

    def _extract_raw_text(self, pdf_path: Path) -> str:
        """用 PyMuPDF 从 PDF 提取原始文本作为 Ground Truth。

        Args:
            pdf_path: PDF 文件路径。

        Returns:
            原始文本。
        """
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            pages_text = []
            for page in doc:
                pages_text.append(page.get_text())
            doc.close()
            return "\n\n".join(pages_text)
        except Exception as e:
            logger.warning("PyMuPDF 提取失败: %s", e)
            return ""

    def _count_pdf_pages(self, pdf_path: Path) -> int:
        """获取 PDF 总页数。"""
        try:
            import fitz
            doc = fitz.open(pdf_path)
            count = len(doc)
            doc.close()
            return count
        except Exception:
            return 0

    def _extract_key_phrases(self, text: str, max_phrases: int = 100) -> List[str]:
        """从原文中提取关键短语用于完整性检查。

        选取中等长度的非重复片段（10-30字符）。
        筛选标准：包含中文字符且合理分段。

        Args:
            text: 原文。
            max_phrases: 最大提取数。

        Returns:
            关键短语列表。
        """
        # 按双换行分段
        segments = re.split(r"\n\s*\n", text)
        phrases = []
        seen = set()

        for seg in segments:
            seg = seg.strip()
            if len(seg) < 10 or len(seg) > 80:
                continue
            # 必须含中文
            if not re.search(r"[\u4e00-\u9fff]", seg):
                continue
            # 去重
            key = seg[:30]
            if key not in seen:
                seen.add(key)
                phrases.append(seg)

            if len(phrases) >= max_phrases:
                break

        return phrases
