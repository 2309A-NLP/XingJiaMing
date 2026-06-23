"""
01_chunk.py — 文档分段脚本
将金融文档切成适合 Embedding 模型的小段落

用法: conda run -n emb python scripts/01_chunk.py
"""

import os
import json
import re
from pathlib import Path

# ============ 配置 ============
CHUNK_SIZE = 250        # 每段目标字数（中文约125字）
OVERLAP = 50            # 段落之间重叠字数
MIN_CHUNK_LEN = 50      # 太短的段落丢弃
RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
OUTPUT_FILE = Path(__file__).parent.parent / "data" / "chunks.jsonl"


def clean_text(text: str) -> str:
    """清理文本：去掉多余空行、页码标记等"""
    # 去掉 "## 第 X 页" 标记
    text = re.sub(r'##\s*第\s*\d+\s*页', '', text)
    # 去掉连续空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    # 去掉行首尾空格
    lines = [line.strip() for line in text.split('\n')]
    return '\n'.join(lines)


def split_by_paragraph(text: str) -> list[str]:
    """按段落切分（双换行分隔）"""
    paragraphs = re.split(r'\n{2,}', text)
    return [p.strip() for p in paragraphs if p.strip()]


def merge_short_paragraphs(paragraphs: list[str], target_size: int) -> list[str]:
    """把太短的段落合并，太长的段落拆分"""
    result = []
    buffer = ""

    for para in paragraphs:
        # 如果当前 buffer + 新段落 还没到目标大小，就合并
        if buffer and len(buffer) + len(para) < target_size:
            buffer += "\n\n" + para
        elif buffer:
            # buffer 已经够大，存起来
            result.append(buffer)
            buffer = para
        else:
            buffer = para

    if buffer:
        result.append(buffer)

    return result


def split_long_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """对超长文本按固定长度切分，带重叠"""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        # 尝试在标点符号处断开
        if end < len(text):
            # 往回找最近的标点
            for punct in ['。', '！', '？', '；', '，', '.', '!', '?']:
                pos = text.rfind(punct, start + chunk_size // 2, end)
                if pos > start:
                    end = pos + 1
                    break
        chunk = text[start:end].strip()
        if chunk and len(chunk) >= MIN_CHUNK_LEN:
            chunks.append(chunk)
        start = end - overlap if end < len(text) else end

    return chunks


def chunk_document(filepath: Path) -> list[dict]:
    """将一个文档切成多个段落"""
    # 读取文件
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 清理文本
    content = clean_text(content)

    # 去掉标题行（第一行通常是文件名重复）
    lines = content.split('\n')
    if lines and lines[0].startswith('# '):
        content = '\n'.join(lines[1:])

    # 按段落切分
    paragraphs = split_by_paragraph(content)

    # 合并短段落
    merged = merge_short_paragraphs(paragraphs, CHUNK_SIZE)

    # 对仍然超长的段落进一步切分
    final_chunks = []
    for para in merged:
        if len(para) > CHUNK_SIZE * 2:
            final_chunks.extend(split_long_text(para, CHUNK_SIZE, OVERLAP))
        else:
            final_chunks.append(para)

    # 生成 chunk 对象
    doc_name = filepath.stem
    chunks = []
    for i, text in enumerate(final_chunks):
        if len(text) >= MIN_CHUNK_LEN:
            chunks.append({
                "chunk_id": f"{doc_name}_chunk_{i:04d}",
                "text": text,
                "source": doc_name,
                "char_count": len(text),
            })

    return chunks


def main():
    print("=" * 50)
    print("文档分段脚本")
    print("=" * 50)

    # 收集所有 md 文件
    md_files = sorted(RAW_DIR.glob("*.md"))
    print(f"\n找到 {len(md_files)} 个文档")

    all_chunks = []
    for filepath in md_files:
        chunks = chunk_document(filepath)
        all_chunks.extend(chunks)
        print(f"  {filepath.stem[:30]}... → {len(chunks)} 个段落")

    # 保存
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + '\n')

    # 统计
    print(f"\n{'=' * 50}")
    print(f"总段落数: {len(all_chunks)}")
    print(f"平均字数: {sum(c['char_count'] for c in all_chunks) / len(all_chunks):.0f}")
    print(f"输出文件: {OUTPUT_FILE}")

    # 展示几个样例
    print(f"\n--- 样例段落 ---")
    for i in [0, len(all_chunks) // 2, -1]:
        c = all_chunks[i]
        print(f"\n[{c['chunk_id']}] ({c['char_count']}字)")
        print(c['text'][:150] + "...")


if __name__ == "__main__":
    main()
