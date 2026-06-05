"""递归字符分块 + 父子块策略（优化版）

优化点：
1. 表格保护：表格整个作为一块，不被切断
2. 语义完整性：按句子边界分块，不切断句子
3. 动态分块大小：正文500-800，表格整个保留
4. 重叠策略：按句子边界重叠
"""
from __future__ import annotations
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
    # 至少有表头和一行数据，且包含 | 分隔符
    if len(lines) >= 2:
        pipe_count = sum(1 for line in lines if '|' in line)
        if pipe_count >= len(lines) * 0.5:  # 超过一半的行包含 |
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
        # 判断是否是表格行：包含 | 的都算，分隔线也是表格的一部分
        is_table_line = '|' in line
        
        if is_table_line:
            if not in_table:
                in_table = True
                current_table = []
            current_table.append(line)
        else:
            if in_table:
                # 表格结束
                if len(current_table) >= 2:
                    tables.append('\n'.join(current_table))
                else:
                    # 不是真正的表格，放回结果
                    result_lines.extend(current_table)
                current_table = []
                in_table = False
            result_lines.append(line)
    
    # 处理最后一个表格
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
    
    # 按句子分割
    sentences = re.split(r'(?<=[。；.？！?!，,])\s*', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        # 如果单个句子就超过最大长度，需要进一步分割
        if len(sentence) > max_chars:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            # 对超长句子按逗号分割
            sub_chunks = split_by_commas(sentence, max_chars)
            chunks.extend(sub_chunks)
            continue
        
        # 尝试添加到当前块
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
            # 如果单个部分还是太长，强制按字符分割
            if len(part) > max_chars:
                for i in range(0, len(part), max_chars):
                    chunks.append(part[i:i + max_chars])
            else:
                current_chunk = part
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks


def smart_overlap(chunks: List[str], overlap_chars: int) -> List[str]:
    """按句子边界重叠，更自然"""
    if len(chunks) <= 1 or overlap_chars <= 0:
        return chunks
    
    result = [chunks[0]]
    
    for i in range(1, len(chunks)):
        prev_chunk = chunks[i - 1]
        current_chunk = chunks[i]
        
        # 从上一个块的末尾找句子边界
        overlap_text = ""
        if len(prev_chunk) > overlap_chars:
            # 从末尾向前找句子边界
            tail = prev_chunk[-overlap_chars:]
            # 找最后一个句子结束符
            last_ending = -1
            for j, char in enumerate(tail):
                if char in SENTENCE_ENDINGS:
                    last_ending = j
            
            if last_ending >= 0:
                overlap_text = tail[last_ending + 1:].strip()
            else:
                # 没找到句子边界，直接截取
                overlap_text = tail
        
        if overlap_text:
            result.append(overlap_text + current_chunk)
        else:
            result.append(current_chunk)
    
    return result


def recursive_split(text: str, max_chars: int) -> List[str]:
    """递归分割文本（保留原有逻辑，增加表格保护）"""
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


class Chunker:
    """优化版分块器"""
    
    def __init__(self, max_chars: int = 600, overlap: int = 50, min_chars: int = 30):
        """初始化分块器
        
        Args:
            max_chars: 正文最大字符数（默认600，比原来的300更宽松）
            overlap: 重叠字符数（默认50，按句子边界重叠）
            min_chars: 最小字符数
        """
        self._max = max_chars
        self._overlap = overlap
        self._min = min_chars

    def chunk(self, md: str) -> Tuple[List[Chunk], List[Chunk]]:
        """执行分块"""
        sections = split_sections(md)
        parents, children, pi, ci = [], [], 0, 0

        for sec in sections:
            # 先从原始内容提取页码，再清除注释
            pages = extract_pages(sec["content"])
            clean = strip_meta(sec["content"])
            if len(clean) < self._min:
                continue

            parent = Chunk(content=clean, chunk_id="p%04d" % pi, is_parent=True,
                           metadata={"section_title": sec["title"], "page_numbers": pages})
            parents.append(parent)

            # 提取表格，表格整个保留
            tables, remaining_text = extract_tables(clean)
            
            # 处理表格（整个保留，不切割）
            for table in tables:
                if len(table) >= self._min:
                    children.append(Chunk(
                        content=table, 
                        chunk_id="c%04d" % ci, 
                        parent_id=parent.chunk_id,
                        metadata={"section_title": sec["title"], "page_numbers": pages, "is_table": True}
                    ))
                    ci += 1
            
            # 处理正文（按句子边界分块）
            if remaining_text.strip():
                # 按句子边界分块
                subs = split_by_sentences(remaining_text, self._max)
                
                # 按句子边界重叠
                if self._overlap > 0 and len(subs) > 1:
                    subs = smart_overlap(subs, self._overlap)
                
                for st in subs:
                    if len(st) < self._min:
                        continue
                    children.append(Chunk(
                        content=st, 
                        chunk_id="c%04d" % ci, 
                        parent_id=parent.chunk_id,
                        metadata={"section_title": sec["title"], "page_numbers": pages, "is_table": False}
                    ))
                    ci += 1
            
            pi += 1

        logger.info("分块完成: %d 父块, %d 子块", len(parents), len(children))
        return parents, children