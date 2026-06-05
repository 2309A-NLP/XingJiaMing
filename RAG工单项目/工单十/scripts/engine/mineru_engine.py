"""MinerUEngine - MinerU 布局分析引擎（混合模式 - CLI 方式）

使用 MinerU CLI 直接对 PDF 文件进行布局分析，
从输出目录中读取结果。

在混合模式下，MinerU 只负责布局检测，
OCR 文字识别由 PaddleOCREngine 完成。
"""

from __future__ import annotations
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from PIL import Image
from scripts.engine.base import BaseEngine

logger = logging.getLogger(__name__)


class MinerUEngine(BaseEngine):
    """基于 Magic-PDF CLI 的布局分析引擎。

    通过调用 magic_pdf.tools.cli 命令行工具
    对 PDF 文件进行布局分析，提取布局区域信息。
    """

    def __init__(self, output_dir: str | Path = "./data"):
        """初始化 MinerU 引擎。

        Args:
            output_dir: MinerU 输出目录。
        """
        self._output_dir = Path(output_dir)
        self._available = False
        self._checked = False

    @property
    def name(self) -> str:
        return "mineru"

    def is_available(self) -> bool:
        if self._checked:
            return self._available
        self._checked = True
        try:
            from magic_pdf.tools.cli import cli
            self._available = True
        except Exception as e:
            logger.warning("MinerU CLI 不可用: %s", e)
            self._available = False
        return self._available

    def initialize(self) -> None:
        self.is_available()

    def process_page(self, image: Image.Image, page_no: int) -> str:
        """此方法在混合模式下不使用。

        混合模式下，MinerU 引擎不处理单页，
        而是由 BatchProcessor 直接调用 MinerU CLI 处理整个 PDF。

        Returns:
            空字符串（布局分析由 BatchProcessor 统一调度）。
        """
        return ""

    def analyze_layout(self, pdf_path: str | Path, output_subdir: str = "layout") -> Path:
        """对完整 PDF 进行布局分析。

        调用 MinerU CLI 解析 PDF，从输出目录中提取布局 JSON。

        Args:
            pdf_path: PDF 文件路径。
            output_subdir: 输出子目录名。

        Returns:
            MinerU 输出目录路径。
        """
        pdf_path = Path(pdf_path)
        output_dir = self._output_dir / output_subdir / pdf_path.stem
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info("MinerU 布局分析: %s -> %s", pdf_path.name, output_dir)

        try:
            # 调用 MinerU CLI
            result = subprocess.run(
                [sys.executable, "-m", "magic_pdf.tools.cli",
                 "-p", str(pdf_path),
                 "-o", str(output_dir),
                 "-m", "auto"],
                capture_output=True, text=True, timeout=600
            )

            if result.returncode == 0:
                logger.info("MinerU 布局分析完成: %s", pdf_path.name)

                # 查找生成的 JSON 文件
                json_files = list(output_dir.rglob("*.json"))
                logger.debug("MinerU 输出 %d 个 JSON 文件", len(json_files))

                # 查找 Markdown 文件
                md_files = list(output_dir.rglob("*.md"))
                logger.debug("MinerU 输出 %d 个 MD 文件", len(md_files))
            else:
                logger.warning("MinerU 布局分析失败 (code=%d): %s",
                               result.returncode, result.stderr[:200])

        except subprocess.TimeoutExpired:
            logger.warning("MinerU 布局分析超时: %s", pdf_path.name)
        except Exception as e:
            logger.warning("MinerU 布局分析异常: %s", e)

        return output_dir

    def get_layout_regions(self, output_dir: Path) -> Dict[int, List[Dict]]:
        """从 MinerU 输出目录中提取每页的布局区域。

        扫描 MinerU 的输出文件，为每页提取布局区域（bbox+类别）。

        Args:
            output_dir: MinerU 输出目录。

        Returns:
            每页的布局区域字典 {page_no: [region, ...]}。
        """
        regions_by_page: Dict[int, List[Dict]] = {}

        # 查找所有 JSON 文件
        for json_path in sorted(output_dir.rglob("*.json")):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._parse_json_for_regions(data, regions_by_page)
            except Exception as e:
                logger.debug("解析 %s 失败: %s", json_path.name, e)
                continue

        return regions_by_page

    def _parse_json_for_regions(
        self,
        data: Any,
        regions_by_page: Dict[int, List[Dict]],
    ) -> None:
        """递归解析 JSON 数据，提取布局区域。

        Args:
            data: JSON 数据（dict 或 list）。
            regions_by_page: 每页的区域列表（输出参数）。
        """
        if isinstance(data, dict):
            # 检查是否有页面信息和布局检测结果
            page_no = data.get("page_no") or data.get("page_num") or data.get("page_number")

            # 提取布局检测结果
            for key in ["layout_dets", "layout_res", "bbox_list", "regions"]:
                dets = data.get(key)
                if dets and isinstance(dets, list):
                    page = page_no or 0
                    if page not in regions_by_page:
                        regions_by_page[page] = []
                    for det in dets:
                        region = self._normalize_region(det)
                        if region:
                            regions_by_page[page].append(region)

            # 递归处理嵌套
            for v in data.values():
                self._parse_json_for_regions(v, regions_by_page)

        elif isinstance(data, list):
            for item in data:
                self._parse_json_for_regions(item, regions_by_page)

    def _normalize_region(self, det: Any) -> Optional[Dict]:
        """规范化单条区域数据。

        Args:
            det: 区域检测结果。

        Returns:
            规范化的区域字典。
        """
        if isinstance(det, dict):
            bbox = det.get("bbox") or det.get("box") or det.get("poly")
            category = det.get("category") or det.get("type") or det.get("label", "unknown")
            score = det.get("score") or det.get("confidence", 1.0)
            if bbox and len(bbox) >= 4:
                return {
                    "bbox": [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])],
                    "category": str(category),
                    "score": float(score),
                }
        return None

    def cleanup(self) -> None:
        import gc
        gc.collect()
