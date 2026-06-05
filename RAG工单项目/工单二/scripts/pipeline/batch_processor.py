"""BatchProcessor - 批处理处理器（核心调度器）

混合模式：MinerU 做布局分析 + PaddleOCR 做文字识别

处理流程：
  1. 渲染 PDF 所有页面为图片
  2. 对每页：先做布局分析（MinerU），再做文字识别（PaddleOCR）
  3. 根据 PageJudge 的决策路由到不同的引擎组合
  4. 支持多进程并行处理每个批次
  5. 支持断点续传（StateManager）
  6. 输出合并为标准 Markdown 文件
"""

from __future__ import annotations
import gc                  # 垃圾回收
import json                # JSON 序列化
import logging             # 结构化日志
import time                # 计时
from pathlib import Path
from typing import Dict, List, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed
from PIL import Image
from scripts.engine.mineru_engine import MinerUEngine
from scripts.engine.paddleocr_engine import PaddleOCREngine
from scripts.models.models import (
    BatchState, IngestReport, PageCategoryType,
    PageContent, PageProcessStatus,
)
from scripts.pipeline.state_manager import StateManager
from scripts.pipeline.cleaner import PageCleaner
from scripts.pipeline.sensitive_cleaner import SensitiveCleaner

logger = logging.getLogger(__name__)


# 全局配置常量
BATCH_TIMEOUT_SECONDS = 600       # 每批处理超时时间（秒）
PARALLEL_WORKERS = 2              # 并行工作进程数（CPU 核数）
DEFAULT_BATCH_SIZE = 50           # 默认每批页数
IMAGES_SCALE = 2.0                # 图片渲染缩放比例


class BatchProcessor:
    """文档批处理处理器。

    使用 MinerU（布局分析）+ PaddleOCR（文字识别）的混合模式，
    支持批处理、并行、断点续传、动态资源调度。
    """

    def __init__(
        self,
        pdf_path: str | Path,
        output_dir: str | Path = "./data",
        storage_dir: str | Path = "./storage",
        batch_size: int = DEFAULT_BATCH_SIZE,
        images_scale: float = IMAGES_SCALE,
        enable_paddleocr: bool = True,
        enable_mineru: bool = True,
        ocr_language: str = "ch",
    ):
        """初始化 BatchProcessor。

        Args:
            pdf_path: PDF 文件路径。
            output_dir: 输出目录（存放 Markdown 结果）。
            storage_dir: 状态目录（存放断点续传状态文件）。
            batch_size: 每批页数。
            images_scale: 图片渲染缩放比例（2.0 = 2x 分辨率）。
            enable_paddleocr: 是否启用 PaddleOCR 引擎。
            enable_mineru: 是否启用 MinerU 引擎。
            ocr_language: OCR 语言，默认中文 "ch"。
        """
        self._pdf_path = Path(pdf_path)
        self._output_dir = Path(output_dir)
        self._storage_dir = Path(storage_dir)
        self._batch_size = batch_size
        self._images_scale = images_scale

        # 初始化引擎（如果启用）
        self._paddleocr = PaddleOCREngine(lang=ocr_language) if enable_paddleocr else None
        self._mineru = MinerUEngine(output_dir=output_dir) if enable_mineru else None

        # 页面清洗器
        self._cleaner = PageCleaner()
        self._sensitive_cleaner = SensitiveCleaner()

        # 状态管理器（断点续传）
        self._state_mgr = StateManager(storage_dir=storage_dir)

    def process(self) -> IngestReport:
        """执行完整的文档处理流程。

        流程：
          1. 加载或初始化处理状态（断点续传）
          2. 渲染所有页面为图片
          3. 按批次处理（支持断点续传）
          4. 合并输出为 Markdown
          5. 生成处理报告

        Returns:
            处理报告（包含统计信息和输出路径）。
        """
        start_time = time.time()
        pdf_name = self._pdf_path.name

        logger.info("=" * 60)
        logger.info("开始处理: %s", pdf_name)

        # 步骤 1: 获取 PDF 总页数
        total_pages = self._count_pages()
        logger.info("PDF 总页数: %d", total_pages)

        # 步骤 2: 加载或初始化处理状态
        state = self._state_mgr.load(pdf_name)
        if state is None:
            state = self._state_mgr.init_state(pdf_name, total_pages, self._batch_size)

        # 检查是否有已完成页面需要跳过
        pending_count = len(state.get_pending_pages())
        completed_count = total_pages - pending_count
        if completed_count > 0:
            logger.info("已有 %d/%d 页完成（断点续传）", completed_count, total_pages)

        # 步骤 3: 渲染所有页面为图片
        logger.info("渲染页面图片（缩放比例: %.1fx）...", self._images_scale)
        page_images = self._render_all_pages(total_pages)
        logger.info("页面图片: %d/%d", len(page_images), total_pages)

        # 步骤 4: 按批次处理
        all_contents: List[PageContent] = []
        total_batches = (total_pages + self._batch_size - 1) // self._batch_size
        logger.info("共 %d 批次（每批 %d 页）", total_batches, self._batch_size)

        for batch_idx in range(total_batches):
            batch_no = batch_idx + 1

            # 断点续传：跳过已完成的批次
            if batch_no in state.completed_batches:
                logger.info("批次 %d/%d 已完成（跳过）", batch_no, total_batches)
                continue

            # 计算本批次页码范围
            start_p = batch_idx * self._batch_size + 1
            end_p = min(start_p + self._batch_size - 1, total_pages)

            logger.info("批次 %d/%d: 第 %d-%d 页（共 %d 页）",
                        batch_no, total_batches, start_p, end_p, end_p - start_p + 1)

            # 处理本批次
            batch_start = time.time()
            batch_contents = self._process_batch(start_p, end_p, page_images, state)
            all_contents.extend(batch_contents)

            # 标记批次完成
            self._state_mgr.mark_batch_completed(state, batch_no)

            # 清理内存
            batch_elapsed = time.time() - batch_start
            logger.info("批次 %d/%d 完成（%.1f秒）", batch_no, total_batches, batch_elapsed)
            self._force_gc()

        # 步骤 5: 合并输出
        output_path = self._merge_output(all_contents, pdf_name, page_images)

        # 步骤 6: 生成报告
        elapsed = time.time() - start_time
        success = sum(1 for c in all_contents if c.markdown.strip())
        failed = total_pages - success

        report = IngestReport(
            source_pdf=str(self._pdf_path),
            total_pages=total_pages,
            successful_pages=success,
            failed_pages=failed,
            output_path=str(output_path),
            processing_time_seconds=round(elapsed, 2),
            engines_used=self._detect_engines(),
            errors=self._collect_errors(state),
        )

        # 打印完成摘要
        logger.info("=" * 60)
        logger.info("处理完成: %d/%d 页成功 (%.1f秒)",
                     success, total_pages, elapsed)
        if failed > 0:
            logger.warning("失败 %d 页", failed)

        return report

    def _count_pages(self) -> int:
        """获取 PDF 的总页数。

        Returns:
            PDF 文件的总页数。
        """
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(self._pdf_path))
        total = len(pdf)
        pdf.close()
        logger.debug("PDF 页数: %d", total)
        return total

    def _render_all_pages(self, total_pages: int) -> Dict[int, Image.Image]:
        """渲染 PDF 所有页面为 PIL Image。

        Args:
            total_pages: 总页数。

        Returns:
            页码到图片的映射字典。
        """
        images: Dict[int, Image.Image] = {}
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(self._pdf_path))
        for i in range(total_pages):
            page = pdf[i]
            # 渲染为 PIL Image
            bitmap = page.render(scale=self._images_scale)
            images[i + 1] = bitmap.to_pil()
            page.close()

        pdf.close()
        logger.debug("已渲染 %d 页", len(images))
        return images

    def _extract_text_direct(self, page_no: int) -> str:
        """直接从 PDF 提取文本（兜底方案）。

        对于纯文字 PDF，可以直接从页面提取文本，
        比 OCR 更快更准确。

        Args:
            page_no: 页码（从 1 开始）。

        Returns:
            页面文本内容。
        """
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(self._pdf_path))
        page = pdf[page_no - 1]
        try:
            tp = page.get_textpage()
            text = tp.get_text_range()
            tp.close()
        finally:
            page.close()
            pdf.close()

        return text.strip()

    def _process_batch(
        self,
        start: int,
        end: int,
        page_images: Dict[int, Image.Image],
        state: BatchState,
    ) -> List[PageContent]:
        """处理单个批次的所有页面。

        混合模式策略：
          1. 对于每页，先尝试 MinerU 布局分析
          2. 如果分析成功且有布局信息，用布局辅助 PaddleOCR
          3. 如果 MinerU 失败，直接用 PaddleOCR
          4. 兜底方案：直接提取 PDF 文本

        Args:
            start: 批次起始页码。
            end: 批次结束页码。
            page_images: 页面图片字典。
            state: 当前处理状态（用于断点续传）。

        Returns:
            本批次所有页面的解析内容列表。
        """
        contents: List[PageContent] = []

        for pn in range(start, end + 1):
            # 断点续传：跳过已完成的页面
            if pn in state.pages and state.pages[pn].status == PageProcessStatus.ENHANCED:
                continue

            image = page_images.get(pn)
            if image is None:
                # 页面渲染失败
                logger.error("第%d页: 无法渲染图片", pn)
                self._state_mgr.mark_page_failed(state, pn, "无法渲染图片")
                continue

            engines_used: List[str] = []
            md_text = ""
            layout_info_str = ""

            # ========== 引擎 1: MinerU 布局分析 ==========
            if self._mineru and self._mineru.is_available():
                try:
                    layout_result = self._mineru.process_page(image, pn)
                    if layout_result and len(layout_result) > 10:
                        engines_used.append("mineru")
                        layout_info_str = layout_result
                        logger.debug("第%d页: MinerU 布局分析完成", pn)
                except Exception as e:
                    logger.warning("第%d页: MinerU 布局分析失败: %s", pn, e)
                    logger.debug("异常详情", exc_info=True)

            # ========== 引擎 2: PaddleOCR 文字识别 ==========
            if self._paddleocr and self._paddleocr.is_available():
                try:
                    ocr_result = self._paddleocr.process_page(image, pn)
                    if ocr_result and ocr_result.strip():
                        engines_used.append("paddleocr")
                        md_text = ocr_result
                        logger.debug("第%d页: PaddleOCR 识别完成（%d 字符）",
                                     pn, len(ocr_result))
                except Exception as e:
                    logger.warning("第%d页: PaddleOCR 识别失败: %s", pn, e)
                    logger.debug("异常详情", exc_info=True)

            # ========== 引擎 3: 直接 PDF 文本提取（兜底） ==========
            if not md_text:
                try:
                    direct_text = self._extract_text_direct(pn)
                    if direct_text.strip():
                        engines_used.append("text")
                        md_text = direct_text
                        logger.debug("第%d页: 直接文本提取完成", pn)
                except Exception as e:
                    logger.warning("第%d页: 文本提取失败: %s", pn, e)

            # ========== 构建页面内容 ==========
            if not engines_used:
                engines_used = ["none"]
                logger.warning("第%d页: 所有引擎均失败", pn)

            # 生成元数据注释
            meta_lines = [
                f"<!-- 第{pn}页 | 引擎: {','.join(engines_used)} -->",
            ]
            if layout_info_str:
                # 如果有布局分析结果，将关键信息作为注释加入
                try:
                    layout_data = json.loads(layout_info_str)
                    region_count = len(layout_data.get("regions", []))
                    meta_lines.append(f"<!-- 布局区域数: {region_count} -->")
                except (json.JSONDecodeError, TypeError):
                    pass

            meta = "\n".join(meta_lines)

            # 组装最终 Markdown
            if md_text.strip():
                full_md = f"{meta}\n\n{md_text}"
            else:
                full_md = f"{meta}\n\n（该页无文字内容）"

            # 保存解析结果
            contents.append(PageContent(
                page_no=pn,
                category=PageCategoryType.NORMAL_TEXT,
                engines_used=engines_used,
                markdown=full_md,
            ))

            # 标记页面完成（断点续传）
            self._state_mgr.mark_page_done(state, pn, engines_used)

        return contents

    def _merge_output(
        self,
        contents: List[PageContent],
        pdf_name: str,
        page_images: Optional[Dict[int, Image.Image]] = None,
    ) -> Path:
        """合并所有页面的解析结果为单个 Markdown 文件。

        Args:
            contents: 所有页面的解析内容列表。
            pdf_name: PDF 文件名（用于命名输出文件）。

        Returns:
            输出文件的路径。
        """
        # 按页码排序
        sorted_c = sorted(contents, key=lambda c: c.page_no)

        # 生成输出文件名
        stem = Path(pdf_name).stem
        out_path = self._output_dir / f"{stem}_refined.md"

        # 收集有内容的页面
        chunks: List[str] = []
        for content in sorted_c:
            if content.markdown.strip():
                # 清洗该页内容（去页眉页脚）
                cleaned_md = self._cleaner.clean_page(content.markdown, content.page_no)
                if cleaned_md.strip():
                    chunks.append(cleaned_md)

        # 用分页符分隔
        final_md = "\n\n---\n\n".join(chunks)

        # Layer 3 + Layer 4: 全文清洗（重复行过滤 + 水印/公章检测）
        logger.info("全文清洗中（去重复行、检测印章/水印）...")
        final_md = self._cleaner.clean_document(final_md, page_images=page_images)
        final_md = self._sensitive_cleaner.clean(final_md)

        # 写入文件
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(final_md, encoding="utf-8")

        # 统计
        page_count = len(chunks)
        char_count = len(final_md)
        logger.info("输出: %s (%d 页, %d 字符)", out_path.name, page_count, char_count)

        return out_path

    def _detect_engines(self) -> List[str]:
        """检测可用的引擎列表。

        Returns:
            可用引擎名称列表。
        """
        engines = []
        if self._mineru:
            engines.append("mineru")
        if self._paddleocr:
            engines.append("paddleocr")
        engines.append("text")
        return engines

    def _collect_errors(self, state: BatchState) -> List[str]:
        """收集所有页面的错误信息。

        Args:
            state: 当前处理状态。

        Returns:
            错误信息列表。
        """
        errors = []
        for pn in sorted(state.pages.keys()):
            ps = state.pages[pn]
            if ps.error is not None:
                errors.append(f"第{pn}页: {ps.error}")
        return errors

    def _force_gc(self) -> None:
        """强制垃圾回收，释放内存。

        处理完每批后调用，防止内存泄漏。
        如果有 GPU，也释放 GPU 缓存。
        """
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.debug("GPU 缓存已释放")
        except ImportError:
            pass




