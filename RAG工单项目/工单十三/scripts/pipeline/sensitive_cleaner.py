"""敏感信息清洗器 (SensitiveCleaner)

功能:
  对文本进行敏感信息检测与脱敏处理。
  词库从 JSON 文件加载，支持热更新和自定义。

词库结构:
  scripts/pipeline/sensitive_words.json

使用方法:
  # 默认使用内置词库
  cleaner = SensitiveCleaner()
  text = cleaner.clean("联系: 13800138000")

  # 指定自定义词库文件
  cleaner = SensitiveCleaner(word_file="my_words.json")
  
  # 运行时热更新（修改JSON文件后自动重载）
  text = cleaner.clean("新文本")
  # 如果 sensitive_words.json 修改时间变了，自动重载
"""

from __future__ import annotations
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 默认词库路径（与脚本同目录）
_DEFAULT_WORD_FILE = Path(__file__).parent / "sensitive_words.json"


class SensitiveCleaner:
    """敏感信息清洗器。"""

    def __init__(self, word_file: Optional[str] = None):
        """初始化清洗器。

        Args:
            word_file: 词库 JSON 文件路径。None = 使用内置默认词库。
        """
        self._word_file = Path(word_file) if word_file else _DEFAULT_WORD_FILE
        self._last_mtime: float = 0
        self._compiled_rules: List[Tuple[re.Pattern, str]] = []
        self._compiled_words: Dict[str, str] = {}
        self._word_re: Optional[re.Pattern] = None
        self._stats: Dict[str, int] = {}

        # 初次加载
        self._load_word_file()

    def clean(self, text: str) -> str:
        """对文本进行敏感信息脱敏。

        Args:
            text: 输入文本。

        Returns:
            脱敏后的文本。
        """
        # 热更新检测
        self._check_reload()

        # 正则脱敏
        for pattern, replacement in self._compiled_rules:
            text = pattern.sub(replacement, text)

        # 敏感词匹配
        if self._word_re:
            def replace_word(match):
                word = match.group(0)
                replacement = self._compiled_words.get(word, "[敏感词已过滤]")
                self._stats[replacement] += 1
                return replacement
            text = self._word_re.sub(replace_word, text)

        return text

    def clean_file(self, input_path: str, output_path: Optional[str] = None) -> str:
        """对文件进行脱敏。

        Args:
            input_path: 输入文件路径。
            output_path: 输出文件路径（None = 覆盖原文件）。
        """
        p = Path(input_path)
        text = p.read_text(encoding="utf-8")
        cleaned = self.clean(text)
        out = Path(output_path) if output_path else p
        out.write_text(cleaned, encoding="utf-8")
        logger.info("敏感信息清洗完成: %s", out.name)
        return cleaned

    def reload(self) -> None:
        """手动重新加载词库。"""
        self._load_word_file()
        logger.info("词库已重新加载: %s", self._word_file.name)

    def get_stats(self) -> Dict[str, int]:
        """获取脱敏统计。"""
        return dict(self._stats)

    def report(self) -> str:
        """生成统计报告。"""
        active = {k: v for k, v in self._stats.items() if v > 0}
        if not active:
            return "敏感信息清洗统计: 无敏感信息"
        lines = ["敏感信息清洗统计:"]
        for key, count in sorted(active.items()):
            lines.append(f"  {key}: {count} 次")
        return "\n".join(lines)

    # ─── 内部方法 ─────────────────────────────────

    def _load_word_file(self) -> None:
        """从 JSON 文件加载词库。"""
        if not self._word_file.exists():
            logger.warning("词库文件不存在: %s", self._word_file)
            self._compiled_rules = []
            self._compiled_words = {}
            self._word_re = None
            return

        with open(self._word_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._last_mtime = os.path.getmtime(self._word_file)
        self._stats = {}

        # 加载正则规则
        self._compiled_rules = []
        patterns_data = data.get("patterns", {})
        for name, config in patterns_data.items():
            if not config.get("enabled", True):
                continue
            replacement = config.get("replacement", "[已脱敏]")
            for rule_str in config.get("rules", []):
                try:
                    self._compiled_rules.append((re.compile(rule_str), replacement))
                    self._stats[replacement] = 0
                except re.error as e:
                    logger.warning("正则规则编译失败 [%s.%s]: %s", name, rule_str[:20], e)

        # 加载敏感词
        self._compiled_words = {}
        words_data = data.get("sensitive_words", {})
        for name, config in words_data.items():
            if not config.get("enabled", True):
                continue
            replacement = config.get("replacement", "[敏感词已过滤]")
            for word in config.get("words", []):
                self._compiled_words[word] = replacement
                self._stats[replacement] = 0

        # 编译敏感词正则
        if self._compiled_words:
            escaped = [re.escape(w) for w in self._compiled_words.keys()]
            self._word_re = re.compile("|".join(escaped))
        else:
            self._word_re = None

        logger.info("词库加载完成: %d 条正则, %d 个敏感词",
                     len(self._compiled_rules), len(self._compiled_words))

    def _check_reload(self) -> None:
        """检查词库文件是否更新，自动热重载。"""
        try:
            mtime = os.path.getmtime(self._word_file)
            if mtime > self._last_mtime:
                logger.info("词库已更新，自动重载...")
                self._load_word_file()
        except (OSError, FileNotFoundError):
            pass
