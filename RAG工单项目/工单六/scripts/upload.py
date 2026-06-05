"""文档解析入口 (Ingest CLI)"""
from __future__ import annotations
import argparse
import logging
import sys
import os
from pathlib import Path
from scripts.pipeline.batch_processor import BatchProcessor

# ============================================================
# 设置 AI 模型缓存路径到 E 盘（避免 C 盘空间不足和权限问题）
# ============================================================
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)

# PaddleX 模型目录（含 PaddleOCR 检测/识别模型）
os.environ["PADDLEX_HOME"] = os.path.join(_PROJECT_ROOT, "models_cache", "paddlex")

# MinerU (Magic-PDF) 配置文件
os.environ["MAGIC_PDF_CONFIG"] = os.path.join(_PROJECT_ROOT, "models_cache", "magic-pdf.json")

# HuggingFace 模型缓存（含 Docling Layout 等模型）
os.environ["HF_HOME"] = os.path.join(_PROJECT_ROOT, "models_cache", "huggingface")

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MinerU + PaddleOCR 双引擎 PDF 解析工具")
    parser.add_argument("--pdf", type=str, default=None, help="指定PDF文件")
    parser.add_argument("--data-dir", type=str, default="./data", help="数据目录")
    parser.add_argument("--storage-dir", type=str, default="./storage", help="状态目录")
    parser.add_argument("--batch-size", type=int, default=50, help="每批页数(默认50)")
    parser.add_argument("--no-paddleocr", action="store_true", help="禁用PaddleOCR")
    parser.add_argument("--no-mineru", action="store_true", help="禁用MinerU")
    parser.add_argument("--verbose", "-v", action="store_true", help="调试日志")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")

    kwargs = {"storage_dir": args.storage_dir, "batch_size": args.batch_size,
              "enable_paddleocr": not args.no_paddleocr, "enable_mineru": not args.no_mineru}

    if args.pdf:
        pdf_path = Path(args.data_dir) / args.pdf
        if not pdf_path.exists():
            logger.error("文件不存在: %s", pdf_path.resolve())
            sys.exit(1)
        logger.info("处理: %s", pdf_path.name)
        BatchProcessor(pdf_path=pdf_path, output_dir=args.data_dir, **kwargs).process()
    else:
        data_path = Path(args.data_dir)
        for pdf in sorted(data_path.glob("*.pdf")):
            logger.info("-" * 50)
            logger.info("处理: %s", pdf.name)
            BatchProcessor(pdf_path=pdf, output_dir=data_path, **kwargs).process()


if __name__ == "__main__":
    main()
