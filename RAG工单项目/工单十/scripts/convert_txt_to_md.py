"""将 TXT 文件（JSON 格式）转换为 Markdown 格式

TXT 文件格式：每行一个 JSON 对象，包含 page, allrow, type, inside 字段
输出格式：Markdown 文件，按页面组织内容
"""
import json
import os
from pathlib import Path
from typing import List, Dict


def parse_txt_file(txt_path: Path) -> List[Dict]:
    """解析 TXT 文件，返回 JSON 对象列表"""
    records = []
    with open(txt_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                records.append(record)
            except json.JSONDecodeError as e:
                print(f"警告: {txt_path.name} 第 {line_num} 行 JSON 解析失败: {e}")
    return records


def records_to_markdown(records: List[Dict], source_name: str) -> str:
    """将记录列表转换为 Markdown 格式"""
    if not records:
        return ""

    # 按页面分组
    pages = {}
    for record in records:
        page = record.get('page', 0)
        if page not in pages:
            pages[page] = []
        pages[page].append(record)

    # 生成 Markdown
    md_lines = []
    md_lines.append(f"# {source_name}\n")

    for page_num in sorted(pages.keys()):
        page_records = pages[page_num]
        md_lines.append(f"\n## 第 {page_num} 页\n")

        for record in page_records:
            content = record.get('inside', '').strip()
            if content:
                md_lines.append(content)

        md_lines.append("")  # 页面之间空行

    return "\n".join(md_lines)


def convert_txt_to_md(txt_dir: Path, output_dir: Path) -> List[Path]:
    """将目录下所有 TXT 文件转换为 Markdown 文件"""
    output_dir.mkdir(parents=True, exist_ok=True)

    converted_files = []
    txt_files = sorted(txt_dir.glob("*.txt"))

    print(f"找到 {len(txt_files)} 个 TXT 文件")

    for txt_path in txt_files:
        print(f"处理: {txt_path.name}")

        # 解析 TXT 文件
        records = parse_txt_file(txt_path)
        if not records:
            print(f"  警告: {txt_path.name} 没有有效记录，跳过")
            continue

        # 提取源名称（去掉扩展名）
        source_name = txt_path.stem

        # 转换为 Markdown
        markdown_content = records_to_markdown(records, source_name)

        # 生成输出文件名：原名_refined.md
        md_filename = f"{source_name}_refined.md"
        md_path = output_dir / md_filename

        # 写入文件
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

        converted_files.append(md_path)
        print(f"  已转换: {md_filename} ({len(records)} 条记录)")

    return converted_files


def main():
    """主函数"""
    # 项目根目录
    project_root = Path(__file__).parent.parent

    # TXT 文件目录
    txt_dir = project_root / "data" / "ccf_competition" / "txt"

    # 输出目录（data 根目录）
    output_dir = project_root / "data"

    if not txt_dir.exists():
        print(f"错误: TXT 目录不存在: {txt_dir}")
        return

    print("=" * 50)
    print("开始转换 TXT 文件为 Markdown 格式")
    print("=" * 50)
    print(f"源目录: {txt_dir}")
    print(f"输出目录: {output_dir}")
    print()

    # 转换文件
    converted_files = convert_txt_to_md(txt_dir, output_dir)

    print()
    print("=" * 50)
    print(f"转换完成! 共转换 {len(converted_files)} 个文件")
    print("=" * 50)

    # 列出转换后的文件
    print("\n转换后的文件:")
    for md_path in converted_files:
        print(f"  - {md_path.name}")


if __name__ == "__main__":
    main()
