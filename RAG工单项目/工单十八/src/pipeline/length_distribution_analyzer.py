from __future__ import annotations

from statistics import median

from src.models.document_models import CollectedDocument


def build_length_distribution(documents: list[CollectedDocument], config: dict) -> dict:
    """输出分位数和长度区间分布。"""

    char_counts = sorted(document.char_count for document in documents)
    if not char_counts:
        return {"quantiles": {}, "buckets": {}}

    return {
        "quantiles": {
            "P25": _percentile(char_counts, 25),
            "P50": _percentile(char_counts, 50),
            "P75": _percentile(char_counts, 75),
            "P90": _percentile(char_counts, 90),
            "P99": _percentile(char_counts, 99),
            "median": median(char_counts),
        },
        "buckets": _bucketize(char_counts, config),
    }


def _percentile(values: list[int], percentile: int) -> int:
    """简单百分位数实现，够当前量级使用。"""

    if not values:
        return 0
    index = round((percentile / 100) * (len(values) - 1))
    return values[index]


def _bucketize(char_counts: list[int], config: dict) -> dict[str, int]:
    """按配置分桶。"""

    bucket_definitions = config.get("length_distribution", {}).get("buckets", [])
    bucket_result = {bucket["name"]: 0 for bucket in bucket_definitions}
    for count in char_counts:
        for bucket in bucket_definitions:
            bucket_min = int(bucket.get("min", 0))
            bucket_max = bucket.get("max")
            if bucket_max is None and count >= bucket_min:
                bucket_result[bucket["name"]] += 1
                break
            if bucket_max is not None and bucket_min <= count <= int(bucket_max):
                bucket_result[bucket["name"]] += 1
                break
    return bucket_result

