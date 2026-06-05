"""递归字符分块 + 父子块策略（优化版）

优化点：
1. 表格保护：表格整个作为一块，不被切断
2. 语义完整性：按句子边界分块，不切断句子
3. 动态分块大小：正文500-800，表格整个保留
4. 重叠策略：按句子边界重叠
5. chunk_id 支持文档前缀，避免多文档 ID 冲突
"""
from __future__ import annotations
import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import List, Tuple

logger = logging.getLogger(__name__)

# 分隔符优先级：标题 > 分隔线 > 段落 > 句子 > 逗号 > 空格
SEPARATORS = [
    "\n# ", "\n## ", "\n### ",
    "\n---\n", "\n\n",
    "。", "；", ".",
    "？", "！", "?", "!",
    "，", ",",
    " ",
]

# 句子结束符（用于按句子边界重叠）
SENTENCE_ENDINGS = {"。", "；", ".", "？", "！", "?", "!", "，", ","}


@dataclass
class Chunk:
    content: str
    chunk_id: str = ""
    parent_id: str = ""
    is_parent: bool = False
    metadata: dict = field(default_factory=dict)


def is_table_block(text: str) -> bool:
    """判断文本块是否是表格"""
    lines = text.strip().split('\n')
    if len(lines) >= 2:
        pipe_count = sum(1 for line in lines if '|' in line)
        if pipe_count >= len(lines) * 0.5:
            return True
    return False


def extract_tables(text: str) -> List[dict]:
    """从文本中提取表格，返回表格列表和剩余文本"""
    tables = []
    lines = text.split('\n')
    current_table = []
    in_table = False
    result_lines = []

    for line in lines:
        is_table_line = '|' in line
        if is_table_line:
            if not in_table:
                in_table = True
                current_table = []
            current_table.append(line)
        else:
            if in_table:
                if len(current_table) >= 2:
                    tables.append('\n'.join(current_table))
                else:
                    result_lines.extend(current_table)
                current_table = []
                in_table = False
            result_lines.append(line)

    if in_table and current_table:
        if len(current_table) >= 2:
            tables.append('\n'.join(current_table))
        else:
            result_lines.extend(current_table)

    return tables, '\n'.join(result_lines)


def split_by_sentences(text: str, max_chars: int) -> List[str]:
    """按句子边界分块，保证不切断句子"""
    if len(text) <= max_chars:
        return [text]

    sentences = re.split(r'(?<=[。；.？！?!，,])\s*', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if len(sentence) > max_chars:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            sub_chunks = split_by_commas(sentence, max_chars)
            chunks.extend(sub_chunks)
            continue

        candidate = current_chunk + sentence if current_chunk else sentence
        if len(candidate) <= max_chars:
            current_chunk = candidate
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def split_by_commas(text: str, max_chars: int) -> List[str]:
    """按逗号分割超长句子"""
    if len(text) <= max_chars:
        return [text]

    parts = re.split(r'(?<=[，,])\s*', text)
    parts = [p.strip() for p in parts if p.strip()]

    chunks = []
    current_chunk = ""

    for part in parts:
        candidate = current_chunk + part if current_chunk else part
        if len(candidate) <= max_chars:
            current_chunk = candidate
        else:
            if current_chunk:
                chunks.append(current_chunk)
            if len(part) > max_chars:
                for i in range(0, len(part), max_chars):
                    chunks.append(part[i:i + max_chars])
            else:
                current_chunk = part

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def smart_overlap(chunks: List[str], overlap_chars: int) -> List[str]:
    """按句子边界重叠"""
    if len(chunks) <= 1 or overlap_chars <= 0:
        return chunks

    result = [chunks[0]]
    for i in range(1, len(chunks)):
        prev = chunks[i - 1]
        # 从上一个块的末尾取 overlap_chars 个字符
        overlap_text = prev[-overlap_chars:]
        # 尝试在句子边界处截断
        for sep in SENTENCE_ENDINGS:
            idx = overlap_text.find(sep)
            if idx >= 0:
                overlap_text = overlap_text[idx + 1:]
                break
        if overlap_text.strip():
            result.append(overlap_text + chunks[i])
        else:
            result.append(chunks[i])

    return result


def recursive_split(text: str, max_chars: int) -> List[str]:
    """递归分块"""
    if len(text) <= max_chars:
        return [text]

    for sep in SEPARATORS:
        parts = text.split(sep)
        if len(parts) <= 1:
            continue
        merged, cur = [], ""
        for part in parts:
            candidate = cur + sep + part if cur else part
            if len(candidate) <= max_chars:
                cur = candidate
            else:
                if cur:
                    merged.append(cur)
                cur = part
        if cur:
            merged.append(cur)
        result = []
        for m in merged:
            result.extend(recursive_split(m, max_chars) if len(m) > max_chars else [m])
        return result

    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]


def split_sections(md: str) -> List[dict]:
    """按 Markdown 标题分割章节"""
    pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    headers = list(pattern.finditer(md))
    if headers:
        return _split_by_headers(md, headers)
    pages = re.split(r"\n---\n", md)
    sections = []
    for i, page in enumerate(pages):
        page = page.strip()
        if not page:
            continue
        m = re.search(r"<!--\s*第(\d+)页", page)
        title = "第%s页" % m.group(1) if m else "第%d部分" % (i + 1)
        sections.append({"title": title, "content": page})
    return sections


def _split_by_headers(md: str, headers) -> List[dict]:
    """按标题分割章节"""
    sections = []
    if headers[0].start() > 0:
        preamble = md[:headers[0].start()].strip()
        if preamble:
            sections.append({"title": "文档开头", "content": preamble})
    for i, m in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(md)
        sections.append({"title": m.group(2).strip(), "content": md[m.start():end].strip()})
    return sections


def extract_pages(text: str) -> List[int]:
    """提取页码"""
    return sorted({int(m.group(1)) for m in re.finditer(r"<!--\s*第(\d+)页", text)})


def strip_meta(text: str) -> str:
    """清除注释"""
    return re.sub(r"<!--.*?-->\s*", "", text, flags=re.DOTALL).strip()


def _make_doc_prefix(source_file: str) -> str:
    """根据文件名生成短前缀，用于 chunk_id 去重"""
    h = hashlib.md5(source_file.encode('utf-8')).hexdigest()[:4]
    return h


class Chunker:
    """优化版分块器"""

    def __init__(self, max_chars: int = 600, overlap: int = 50, min_chars: int = 30):
        self._max = max_chars
        self._overlap = overlap
        self._min = min_chars

    def chunk(self, md: str, source_file: str = '') -> Tuple[List[Chunk], List[Chunk]]:
        """执行分块

        Args:
            md: markdown 文本
            source_file: 文档来源文件名，用于生成唯一 chunk_id
        """
        # 生成文档前缀，避免多文档 chunk_id 冲突
        prefix = _make_doc_prefix(source_file) + '_' if source_file else ''

        sections = split_sections(md)
        parents, children, pi, ci = [], [], 0, 0

        for sec in sections:
            pages = extract_pages(sec["content"])
            clean = strip_meta(sec["content"])
            if len(clean) < self._min:
                continue

            parent = Chunk(
                content=clean,
                chunk_id="%sp%04d" % (prefix, pi),
                is_parent=True,
                metadata={"section_title": sec["title"], "page_numbers": pages, "source_file": source_file}
            )
            parents.append(parent)

            tables, remaining_text = extract_tables(clean)

            for table in tables:
                if len(table) >= self._min:
                    children.append(Chunk(
                        content=table,
                        chunk_id="%sc%04d" % (prefix, ci),
                        parent_id=parent.chunk_id,
                        metadata={"section_title": sec["title"], "page_numbers": pages, "is_table": True, "source_file": source_file}
                    ))
                    ci += 1

            if remaining_text.strip():
                subs = split_by_sentences(remaining_text, self._max)
                if self._overlap > 0 and len(subs) > 1:
                    subs = smart_overlap(subs, self._overlap)

                for st in subs:
                    if len(st) < self._min:
                        continue
                    children.append(Chunk(
                        content=st,
                        chunk_id="%sc%04d" % (prefix, ci),
                        parent_id=parent.chunk_id,
                        metadata={"section_title": sec["title"], "page_numbers": pages, "is_table": False, "source_file": source_file}
                    ))
                    ci += 1

            pi += 1

        logger.info("分块完成: %d 父块, %d 子块 (source: %s)", len(parents), len(children), source_file or 'unknown')
        return parents, children