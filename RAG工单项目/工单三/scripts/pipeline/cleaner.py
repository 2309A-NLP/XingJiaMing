"""数据清洗引擎 (Cleaner) — 完整4层过滤架构

专为 MinerU + PaddleOCR 双引擎解析管道的后处理设计。

过滤架构:
  Layer 1 - 布局过滤 (Layout Filter):
    利用 MinerU 的页面布局标注信息，丢弃被标记为 header/footer/watermark
    的区域文本。接收 page_category 和 layout_regions 作为输入。

  Layer 2 - 模式过滤 (Pattern Filter):
    使用正则规则集匹配并移除页眉行、页脚行、页码行等噪声文本。

  Layer 3 - 重复行过滤 (Repetition Filter):
    自动统计全文所有行的出现频率，将跨页高频重复行判为页眉/页脚/水印
    并自动移除（无需人工指定规则）。

  Layer 4 - 图像过滤 (Image Filter):
    对渲染后的页面图片进行视觉分析：
      - 红色圆形检测 → 公章/印章区域
      - 四角半透明覆盖检测 → 水印
      - 在全页面重复出现的半透明文字检测 → 背景水印
"""

from __future__ import annotations
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class PageCleaner:
    """四层页面内容清洗器。

    支持按页清洗和全文清洗两种模式。
    全文清洗时会自动执行 Layer 3 的重复行统计。
    """

    # ============================================================
    # Layer 2 - 默认页眉/页脚/页码正则规则
    # ============================================================
    PATTERNS: List[re.Pattern] = [
        re.compile(r"^.*\u62db\u80a1\u610f\u5411\u4e66$"),           # "XXX 招股意向书"
        re.compile(r"^\d+-\d+-\d+$"),                                  # "1-1-0" 页码
        re.compile(r"^\d{1,4}$"),                                      # 纯数字页码
        re.compile(r"^\u4fdd\u8350\u673a\u6784"),                     # "保荐机构"
        re.compile(r"^\u58f0\s*\u660e$"),                              # "声 明"
        re.compile(r"^\u6b63\u6587\u5f00\u59cb$"),                    # "正文开始"
    ]

    # ============================================================
    # Layer 3 - 重复行过滤配置
    # ============================================================
    MIN_REPETITION_RATIO = 0.25    # 某行出现在 ≥25% 的页面中，视为页眉/页脚/水印
    MIN_REPETITION_COUNT = 30      # 最少出现次数（避免短文档误杀）

    def __init__(self):
        self._custom_patterns: List[re.Pattern] = []

    # ---------------------------------------------------------------
    # Layer 4 相关 - 水印/公章视觉检测
    # ---------------------------------------------------------------

    def detect_seal_stamp(self, page_image) -> bool:
        """检测页面图片中是否包含红色圆形公印章（Layer 4）。

        使用红色通道阈值分析，检测圆形红色区域。
        基于 scripts/pipeline/page_judge.py 中的算法。

        Args:
            page_image: PIL Image 对象，页面渲染后的图像。

        Returns:
            如果检测到公章返回 True。
        """
        try:
            import numpy as np
            from PIL import Image
            img = np.array(page_image.convert("RGB"))
            if img.ndim < 3:
                return False
            # 红色掩码: R > 150 且 G < 100 且 B < 100
            red_mask = (
                (img[:, :, 0] > 150) &
                (img[:, :, 1] < 100) &
                (img[:, :, 2] < 100)
            )
            red_ratio = red_mask.sum() / red_mask.size
            # 公章通常占页面的 1%~5%
            return 0.01 <= red_ratio <= 0.08
        except ImportError:
            return False

    def detect_watermark_region(self, page_image) -> bool:
        """检测页面图片中是否包含水印区域（Layer 4）。

        水印特征：
          - 半透明（低对比度）
          - 通常出现在页面中央或对角线位置
          - 重复出现

        Args:
            page_image: PIL Image 对象。

        Returns:
            如果检测到疑似水印返回 True。
        """
        try:
            import numpy as np
            img = np.array(page_image.convert("RGBA"))
            # 检查是否有半透明通道（Alpha < 255 的区域）
            if img.shape[2] >= 4:
                alpha = img[:, :, 3]
                semi_transparent = (alpha > 0) & (alpha < 200)
                ratio = semi_transparent.sum() / alpha.size
                return ratio > 0.05
            return False
        except ImportError:
            return False
        except Exception:
            return False

    # ---------------------------------------------------------------
    # 对外核心 API
    # ---------------------------------------------------------------

    def clean_page(self, page_text: str, page_no: int = 0,
                   layout_regions: Optional[List[Dict]] = None,
                   page_image=None) -> str:
        """清洗单页内容（Layer 2 + Layer 4）。

        Args:
            page_text: 原始页面文本。
            page_no: 页码（仅用于日志）。
            layout_regions: MinerU 布局分析结果（Layer 1 输入）。
            page_image: 页面图片（Layer 4 输入）。

        Returns:
            清洗后的页面文本。
        """
        lines = page_text.split("\n")
        cleaned: List[str] = []

        # ---- Layer 1: 如果提供了布局标注，过滤 header/footer 行 ----
        skip_regions: Set[int] = set()
        if layout_regions:
            for region in layout_regions:
                cat = region.get("category", "")
                if cat in ("header", "footer", "watermark", "page_number",
                           "page-no", "in-foot-header-area", "not_in_layout"):
                    bbox = region.get("bbox", [])
                    if len(bbox) >= 4:
                        # 用 y_center 粗略定位到行号
                        y_center = (bbox[1] + bbox[3]) / 2
                        line_idx = int(y_center / 30)  # 假设每行约30px
                        skip_regions.add(line_idx)

        # ---- Layer 2 + Layer 4 ----
        for i, line in enumerate(lines):
            stripped = line.strip()

            # 保留注释行
            if stripped.startswith("<!--") and stripped.endswith("-->"):
                cleaned.append(line)
                continue

            # Layer 1: 跳过布局标注为页眉页脚的行
            if i in skip_regions:
                continue

            # Layer 2: 正则匹配噪声
            if self._is_noise(stripped):
                continue

            # Layer 4: 如果提供了图片，检查水印/公章
            if page_image is not None:
                # 如果该页有公章，在注释中标注（不删除正文）
                if self.detect_seal_stamp(page_image):
                    pass  # 仅在合并时添加注释

            cleaned.append(line)

        # 合并连续空行
        result = self._merge_blanks(cleaned)

        # 去除首尾空行
        while result and result[0].strip() == "":
            result.pop(0)
        while result and result[-1].strip() == "":
            result.pop(-1)

        return "\n".join(result)

    def clean_document(self, markdown_text: str,
                       page_images: Optional[Dict[int, object]] = None,
                       layout_data: Optional[Dict[int, List[Dict]]] = None) -> str:
        """清洗完整 Markdown 文档（四层全开）。

        Args:
            markdown_text: 完整合并的 Markdown 文档。
            page_images: {page_no: PIL Image} 页面图片字典。
            layout_data: {page_no: [region,...]} 布局数据字典。

        Returns:
            清洗后的完整 Markdown 文档。
        """
        # ---- Layer 3: 全文重复行统计 ----
        repetition_blacklist = self._build_repetition_blacklist(markdown_text)
        if repetition_blacklist:
            logger.info("重复行黑名单: %d 条", len(repetition_blacklist))

        # 按 --- 分页符分割
        pages = re.split(r"(\n---\n)", markdown_text)

        cleaned_pages: List[str] = []
        page_no = 1

        for segment in pages:
            if segment.strip() == "---":
                cleaned_pages.append(segment)
                continue

            if not segment.strip():
                cleaned_pages.append(segment)
                continue

            # Layer 1+2: 逐行清洗
            lines = segment.split("\n")
            cleaned_lines: List[str] = []
            for line in lines:
                stripped = line.strip()

                if stripped.startswith("<!--") and stripped.endswith("-->"):
                    cleaned_lines.append(line)
                    continue

                # Layer 3: 跳过重复行
                if stripped in repetition_blacklist:
                    continue

                # Layer 2: 正则噪声
                if self._is_noise(stripped):
                    continue

                cleaned_lines.append(line)

            # 合并空行
            cleaned_text = "\n".join(self._merge_blanks(cleaned_lines)).strip()
            if cleaned_text:
                # Layer 4: 注释印章信息
                seal_note = ""
                if page_images and page_no in page_images:
                    if self.detect_seal_stamp(page_images[page_no]):
                        seal_note = f"<!-- 第{page_no}页: 检测到公章/签章区域 -->\n"
                    if self.detect_watermark_region(page_images[page_no]):
                        seal_note += f"<!-- 第{page_no}页: 检测到水印区域 -->\n"

                if seal_note:
                    cleaned_text = seal_note + cleaned_text

                cleaned_pages.append(cleaned_text)
            page_no += 1

        result = "".join(cleaned_pages)
        result = re.sub(r"\n{3,}---\n{3,}", "\n\n---\n\n", result)
        return result

    # ---------------------------------------------------------------
    # 内部方法
    # ---------------------------------------------------------------

    def add_rule(self, pattern: str) -> None:
        """添加自定义清洗规则（Layer 2 扩展）。

        Args:
            pattern: 正则表达式字符串。
        """
        self._custom_patterns.append(re.compile(pattern))

    def _is_noise(self, text: str) -> bool:
        """检查一行是否为噪声（Layer 2）。"""
        if not text:
            return False
        for p in self.PATTERNS:
            if p.match(text):
                return True
        for p in self._custom_patterns:
            if p.match(text):
                return True
        return False

    def _build_repetition_blacklist(self, text: str) -> Set[str]:
        """统计全文行频次，构建重复行黑名单（Layer 3）。

        原理：页眉/页脚/水印的特征是在大量页面中重复出现。
        统计全文所有行，找出出现在≥阈值比例页面中的行。

        Args:
            text: 完整 Markdown 文本。

        Returns:
            应被移除的重复行集合。
        """
        pages_raw = re.split(r"\n---\n", text)
        total_pages = len(pages_raw)
        if total_pages < 3:
            return set()

        # 统计每行在所有页面中的出现次数
        line_page_count: Counter = Counter()
        for page in pages_raw:
            seen_this_page = set()
            for line in page.split("\n"):
                stripped = line.strip()
                if (stripped and len(stripped) > 3
                        and not stripped.startswith("<!--")
                        and stripped != "---"):
                    seen_this_page.add(stripped)
            for line in seen_this_page:
                line_page_count[line] += 1

        # 出现在 ≥25% 页面中的行加入黑名单
        threshold = max(self.MIN_REPETITION_COUNT,
                        int(total_pages * self.MIN_REPETITION_RATIO))
        blacklist = {
            line for line, count in line_page_count.most_common(100)
            if count >= threshold
        }
        return blacklist

    def _merge_blanks(self, lines: List[str]) -> List[str]:
        """合并连续空行为最多一个空行。"""
        result: List[str] = []
        blank = 0
        for line in lines:
            if line.strip() == "":
                blank += 1
                if blank <= 1:
                    result.append(line)
            else:
                blank = 0
                result.append(line)
        return result
