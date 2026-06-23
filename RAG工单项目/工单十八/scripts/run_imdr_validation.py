from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.api_models import QualityInspectionRequest
from src.pipeline.quality_assessment_service import QualityAssessmentService


def main() -> None:
    """运行 IMDR 小样本验证并输出 JSON 报告。"""

    parser = _build_parser()
    args = parser.parse_args()

    folder_path = Path(args.folder) if args.folder else None
    questions_path = Path(args.questions) if args.questions else None
    selected_documents = _sample_documents(folder_path, args.limit)
    question_count = _count_questions(questions_path) if questions_path else 0
    request = _build_validation_request(
        selected_documents,
        enable_ocr_execution=args.enable_ocr_execution,
    )
    result = QualityAssessmentService().inspect(request)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "folder": str(folder_path) if folder_path else None,
        "questions": str(questions_path) if questions_path else None,
        "sampled_document_count": len(selected_documents),
        "question_count": question_count,
        "status": result.status,
        "progress": result.progress,
        "error_message": result.error_message,
        "ocr_execution_enabled": args.enable_ocr_execution,
        "report": result.report.model_dump() if result.report else None,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"验证完成，报告已输出到 {output_path}")


def _build_parser() -> argparse.ArgumentParser:
    """统一管理 IMDR 验证脚本参数。"""

    parser = argparse.ArgumentParser(description="运行 IMDR documents 数据集质检")
    parser.add_argument(
        "--folder",
        default=os.getenv("IMDR_DOCUMENTS_DIR", ""),
        help="IMDR 文档目录，本地不同时可以用环境变量 IMDR_DOCUMENTS_DIR 覆盖",
    )
    parser.add_argument(
        "--questions",
        default=os.getenv("IMDR_QUESTIONS_PATH", ""),
        help="questions.jsonl 路径，本地不同时可以用环境变量 IMDR_QUESTIONS_PATH 覆盖",
    )
    parser.add_argument(
        "--output",
        default=os.getenv("IMDR_VALIDATION_OUTPUT", "./storage/reports/imdr_validation_report.json"),
        help="输出 JSON 报告路径",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="默认只抽前 N 个样本，避免一上来全量跑太慢",
    )
    parser.add_argument(
        "--enable-ocr-execution",
        action="store_true",
        help="显式开启真实 OCR 执行，默认只做质检和路由建议",
    )
    return parser


def _build_validation_request(selected_documents: list[str], enable_ocr_execution: bool) -> QualityInspectionRequest:
    """把验证脚本参数组装成标准质检请求。"""

    config_overrides = None
    if enable_ocr_execution:
        config_overrides = {"ocr": {"execution_enabled": True}}

    return QualityInspectionRequest(
        file_paths=selected_documents,
        mode="sync",
        include_html_content=False,
        config_overrides=config_overrides,
    )


def _count_questions(path: Path) -> int:
    """这里只做题目数量统计，先把验证闭环串起来。"""

    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _sample_documents(folder: Path | None, limit: int) -> list[str]:
    """先取少量样本，避免默认全量质检太慢。"""

    if folder is None or not folder.exists():
        return []
    supported_extensions = {".pdf", ".docx", ".md", ".txt"}
    files = [
        path
        for path in sorted(folder.iterdir())
        if path.is_file() and path.suffix.lower() in supported_extensions
    ]
    return [str(path) for path in files[:limit]]


if __name__ == "__main__":
    main()
