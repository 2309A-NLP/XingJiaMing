from __future__ import annotations

from collections import Counter

from src.models.document_models import CollectedDocument


def build_format_distribution(documents: list[CollectedDocument]) -> dict[str, dict]:
    """统计格式数量和占比。"""

    total = len(documents)
    counter = Counter(document.extension for document in documents)
    result: dict[str, dict] = {}
    for extension, count in counter.items():
        ratio = round(count / total, 4) if total else 0.0
        result[extension] = {"count": count, "ratio": ratio}
    return result

