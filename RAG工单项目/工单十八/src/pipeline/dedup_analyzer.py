from __future__ import annotations

import hashlib
import re
from collections import defaultdict

from src.models.document_models import CollectedDocument
from src.models.report_models import DuplicateGroup, DuplicateSummary, SimHashCandidate


def analyze_duplicates(documents: list[CollectedDocument], simhash_config: dict | None = None) -> DuplicateSummary:
    """先做 MD5 精确去重，再按配置补近似重复候选。"""

    groups: dict[str, list[str]] = defaultdict(list)
    normalized_texts: dict[str, str] = {}
    for document in documents:
        try:
            md5_hash = hashlib.md5(document.path.read_bytes()).hexdigest()
            document.md5_hash = md5_hash
            groups[md5_hash].append(document.file_name)
        except FileNotFoundError:
            document.md5_hash = None
        normalized_texts[document.file_name] = _normalize_text(document.extracted_text)

    duplicate_groups = [
        DuplicateGroup(md5_hash=md5_hash, files=files)
        for md5_hash, files in groups.items()
        if len(files) > 1
    ]

    simhash_candidates: list[SimHashCandidate] = []
    config = simhash_config or {}
    if config.get("enabled"):
        threshold = int(config.get("distance_threshold", 3))
        hashes = {
            document.file_name: _build_simhash(normalized_texts[document.file_name])
            for document in documents
            if normalized_texts[document.file_name]
        }
        file_names = list(hashes.keys())
        for index, left_name in enumerate(file_names):
            for right_name in file_names[index + 1 :]:
                distance = _hamming_distance(hashes[left_name], hashes[right_name])
                if distance <= threshold:
                    similarity = round(max(0.0, 1 - distance / 64), 4)
                    simhash_candidates.append(
                        SimHashCandidate(
                            files=[left_name, right_name],
                            left_file=left_name,
                            right_file=right_name,
                            distance=distance,
                            similarity=similarity,
                        )
                    )

    return DuplicateSummary(
        exact_duplicate_groups=duplicate_groups,
        simhash_candidates=simhash_candidates,
    )


def _normalize_text(text: str) -> str:
    """这里先把空白和大小写抹平，减少小差异带来的误判。"""

    collapsed = re.sub(r"\s+", " ", text).strip().lower()
    return collapsed


def _build_simhash(text: str) -> int:
    """首版用简单分词 + 64 位 SimHash，够做候选提示。"""

    tokens = _tokenize(text)
    if not tokens:
        return 0

    weights = [0] * 64
    for token in tokens:
        token_hash = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        for bit_index in range(64):
            if token_hash & (1 << bit_index):
                weights[bit_index] += 1
            else:
                weights[bit_index] -= 1

    fingerprint = 0
    for bit_index, weight in enumerate(weights):
        if weight > 0:
            fingerprint |= 1 << bit_index
    return fingerprint


def _tokenize(text: str) -> list[str]:
    """英文优先切成 3-gram，中文按单字兜底。"""

    compact = re.sub(r"[^a-z0-9]+", "", text)
    if compact:
        if len(compact) <= 3:
            return [compact]
        return [compact[index : index + 3] for index in range(len(compact) - 2)]
    return [char for char in text if not char.isspace()]


def _hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()
