from __future__ import annotations

from pathlib import Path

from src.core.settings import get_settings
from src.models.api_models import QualityInspectionRequest
from src.models.document_models import CollectedDocument


def collect_documents(request: QualityInspectionRequest, config: dict) -> tuple[list[CollectedDocument], list[dict]]:
    """收集输入文档并过滤支持的扩展名。"""

    settings = get_settings()
    supported_extensions = {ext.lower() for ext in config.get("supported_extensions", [])}
    selected_paths: list[Path] = []
    errors: list[dict] = []

    if request.file_paths:
        selected_paths = [Path(file_path) for file_path in request.file_paths]
    elif request.folder_path:
        folder = Path(request.folder_path)
        if folder.exists() and folder.is_dir():
            selected_paths = sorted(path for path in folder.iterdir() if path.is_file())
        else:
            errors.append({"type": "input", "message": f"目录不存在: {folder}"})

    documents: list[CollectedDocument] = []
    for path in selected_paths[: settings.max_file_count]:
        if not path.exists():
            errors.append({"type": "input", "message": f"文件不存在: {path}"})
            continue
        extension = path.suffix.lower()
        if extension not in supported_extensions:
            continue
        documents.append(
            CollectedDocument(
                file_name=path.name,
                file_path=str(path),
                extension=extension.lstrip("."),
                size_bytes=path.stat().st_size,
            )
        )
    return documents, errors

