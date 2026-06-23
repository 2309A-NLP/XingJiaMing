from __future__ import annotations

import re

from src.models.document_models import CollectedDocument, SensitiveMatch
from src.models.report_models import SensitiveInfoSummary


def analyze_sensitive_info(documents: list[CollectedDocument], config: dict) -> tuple[SensitiveInfoSummary, list[dict]]:
    """检测敏感信息并生成待审核列表。"""

    sensitive_config = config.get("sensitive_info", {})
    context_window = int(sensitive_config.get("context_window", 12))
    summary = SensitiveInfoSummary(total_matches=0, by_type={})
    pending_reviews: list[dict] = []

    for document in documents:
        for match_type, rule in sensitive_config.items():
            if not isinstance(rule, dict):
                continue
            if not rule.get("enabled", False):
                continue
            pattern = rule.get("pattern")
            if not pattern:
                continue
            for match in re.finditer(pattern, document.extracted_text):
                raw_value = match.group(0)
                masked_value = _mask_value(raw_value)
                context = _build_context(document.extracted_text, match.start(), match.end(), context_window)
                sensitive_match = SensitiveMatch(
                    match_type=match_type,
                    raw_value=raw_value,
                    masked_value=masked_value,
                    context=context,
                    file_name=document.file_name,
                    file_path=document.file_path,
                )
                document.sensitive_matches.append(sensitive_match)
                summary.total_matches += 1
                summary.by_type[match_type] = summary.by_type.get(match_type, 0) + 1
                pending_reviews.append(sensitive_match.model_dump())
    return summary, pending_reviews


def _mask_value(raw_value: str) -> str:
    """对命中值做简单脱敏。"""

    if len(raw_value) <= 4:
        return "*" * len(raw_value)
    return raw_value[:2] + "*" * (len(raw_value) - 4) + raw_value[-2:]


def _build_context(text: str, start: int, end: int, window: int) -> str:
    """截取命中前后文。"""

    left = max(0, start - window)
    right = min(len(text), end + window)
    return text[left:right]

