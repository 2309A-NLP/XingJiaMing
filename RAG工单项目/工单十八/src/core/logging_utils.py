from __future__ import annotations

import logging


def setup_logging(level: str = "INFO") -> None:
    """初始化日志。"""

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

