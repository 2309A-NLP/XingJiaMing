"""PageJudge - 页面智能分类器

核心职责:
  分析每页的特征（内容密度、颜色分布、布局结构），
  决定使用哪个引擎来处理该页面。

决策树逻辑:
  1. 无内容 -> SCANNED_IMAGE -> PaddleOCR
  2. 红色印章 -> SEAL_STAMP -> PaddleOCR
  3. 密集表格(>=3个) -> FINANCIAL_TABLE -> MinerU
  4. 含公式 -> FORMULA_HEAVY -> MinerU
  5. 多栏布局 -> MULTI_COLUMN -> MinerU
  6. 其他 -> NORMAL_TEXT -> 跳过增强
"""

from __future__ import annotations
import logging  # 结构化日志
from typing import Dict, List, Optional
import numpy as np  # 图像像素级分析
from PIL import Image  # 图像处理
from scripts.models.models import PageCategoryType, PageClassificationResult

logger = logging.getLogger(__name__)  # 模块级日志器


class PageJudge:
    """页面智能分类器，通过分析页面视觉特征和内容分布来决策引擎路由。"""

    # ---------- 视觉检测参数 ----------
    SEAL_RED_THRESHOLD = 150      # 红色通道阈值：R 通道大于此值认为可能是印章红色
    SEAL_GREEN_BLUE_MAX = 100     # 非红色通道上限：G/B 通道小于此值排除非红色区域
    SEAL_RATIO_THRESHOLD = 0.02   # 红色像素占比阈值：超过 2% 认为存在印章
    
    MULTICOLUMN_MIN_ITEMS = 8     # 最少元素数：少于 8 个元素不触发多栏检测
    MULTICOLUMN_CLUSTER_GAP = 75  # 栏间距阈值：水平中心点差距超过 75px 视为不同栏
    
    DENSE_TABLE_THRESHOLD = 3     # 表格密集阈值：一页超过 3 个表格视为财务报表

    def classify(
        self,
        page_no: int,
        items_on_page: List,
        page_image: Optional[Image.Image] = None,
    ) -> PageClassificationResult:
        """对单页进行分类，返回分类结果。
        
        Args:
            page_no: 页码。
            items_on_page: 页面上的文档元素列表（Docling item 或其他解析结果）。
            page_image: 页面图片，用于视觉特征检测（印章颜色、布局等）。
        
        Returns:
            分类结果，包含类别、置信度和检测标记。
        """
        # 初始化分类结果对象
        result = PageClassificationResult(page_no=page_no)
        
        # 步骤 1: 统计页面上各类型标签的数量（标题/段落/表格/图片等）
        label_counts = self._count_labels(items_on_page)
        result.label_counts = label_counts

        # 步骤 2: 无任何内容 -> 标记为扫描图片，调用 PaddleOCR
        if not items_on_page:
            result.category = PageCategoryType.SCANNED_IMAGE
            result.confidence = 0.8  # 置信度 0.8：较高但不是绝对确定
            return result

        # 步骤 3: 印章检测（通过分析图片中的红色像素比例）
        if page_image is not None and self._detect_seal(page_image):
            result.has_seal_region = True
            result.category = PageCategoryType.SEAL_STAMP
            result.confidence = 0.85  # 印章特征明显，置信度较高
            return result  # 印章优先级最高，直接返回

        # 步骤 4: 多栏布局检测（通过元素 x 坐标聚类）
        result.is_multicolumn = self._detect_multicolumn(items_on_page)

        # 步骤 5: 公式检测（标签中包含 "formula"）
        if label_counts.get("formula", 0) >= 1:
            result.has_formula = True
            result.category = PageCategoryType.FORMULA_HEAVY
            result.confidence = 0.7
            return result

        # 步骤 6: 密集表格检测（3个以上表格标签）
        table_count = label_counts.get("table", 0)
        if table_count >= self.DENSE_TABLE_THRESHOLD and not result.is_multicolumn:
            # 多栏布局不触发此规则（多栏中表格可能被误拆）
            result.has_dense_table = True
            result.category = PageCategoryType.FINANCIAL_TABLE
            result.confidence = 0.75
            return result

        # 步骤 7: 多栏布局（没有公式/表格时）
        if result.is_multicolumn:
            result.category = PageCategoryType.MULTI_COLUMN
            result.confidence = 0.65
            return result

        # 默认: 正常文字页，无需增强引擎
        result.category = PageCategoryType.NORMAL_TEXT
        result.confidence = 1.0  # 默认最高置信度
        return result

    def classify_batch(
        self,
        get_items_fn,
        total_pages: int,
        page_images: Optional[Dict[int, Image.Image]] = None,
    ) -> List[PageClassificationResult]:
        """批量分类所有页面。
        
        Args:
            get_items_fn: callable(page_no) -> List[items] 获取某页元素的函数。
            total_pages: 总页数。
            page_images: 页面图片字典 {page_no: Image}。
        
        Returns:
            所有页面的分类结果列表，按页码顺序排列。
        """
        results = []
        for pn in range(1, total_pages + 1):
            items = get_items_fn(pn)  # 获取该页的文档元素
            image = page_images.get(pn) if page_images else None
            result = self.classify(pn, items, image)
            results.append(result)
        return results

    # ---------- 内部检测方法 ----------

    def _count_labels(self, items: List) -> Dict[str, int]:
        """统计列表中各类型标签的出现次数。"""
        counts = {}
        for item in items:
            if hasattr(item, "label"):
                # 统一转换为字符串，兼容不同类型
                label = str(item.label) if not isinstance(item.label, str) else item.label
                counts[label] = counts.get(label, 0) + 1
        return counts

    def _detect_seal(self, image: Image.Image) -> bool:
        """通过红色像素占比检测中国公章（红章）。
        
        中国公章通常是红色圆形，红色通道(R)显著高于绿(G)蓝(B)通道。
        检测方法: 统计满足 R>阈值 且 G<上限 且 B<上限 的像素占比。
        """
        img = np.array(image)  # PIL Image -> numpy array
        if img.ndim < 3:  # 灰度图无颜色通道，无法检测
            return False
        
        # 红色掩码: R > 150 且 G < 100 且 B < 100
        red_mask = (
            (img[:, :, 0] > self.SEAL_RED_THRESHOLD) &
            (img[:, :, 1] < self.SEAL_GREEN_BLUE_MAX) &
            (img[:, :, 2] < self.SEAL_GREEN_BLUE_MAX)
        )
        red_ratio = red_mask.sum() / red_mask.size  # 红色像素占比
        return red_ratio > self.SEAL_RATIO_THRESHOLD  # 超过阈值认为有印章

    def _detect_multicolumn(self, items: List) -> bool:
        """通过元素 x 坐标聚类检测多栏布局。
        
        思路: 提取所有元素的水平中心点 x 坐标，
        如果它们聚集在 2-4 个明显分隔的列中，则判定为多栏布局。
        """
        centers = []  # 存储所有元素的水平中心 x 坐标
        for item in items:
            if hasattr(item, "prov") and item.prov:
                for p in item.prov:
                    if hasattr(p, "bbox") and p.bbox is not None:
                        # 计算 bbox 的水平中心: (left + right) / 2
                        centers.append((p.bbox.l + p.bbox.r) / 2)
        
        if len(centers) < self.MULTICOLUMN_MIN_ITEMS:
            return False  # 元素太少，不足以判断
        
        # 简单聚类: 按坐标排序，间距超过阈值则分簇
        sorted_x = sorted(centers)
        clusters = []  # 簇中心点列表
        for x in sorted_x:
            if not clusters or abs(x - clusters[-1]) > self.MULTICOLUMN_CLUSTER_GAP:
                clusters.append(x)
        
        # 2-4 个簇被认为是多栏（少于 2 是单栏，多于 4 是噪声）
        return 2 <= len(clusters) <= 4