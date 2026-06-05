import re
from typing import List, Tuple

def extract_tables(text: str) -> Tuple[List[str], str]:
    """从文本中提取表格，返回表格列表和剩余文本
    
    优化：确保表头和数据在同一个表格块中
    """
    tables = []
    lines = text.split('\n')
    current_table = []
    in_table = False
    result_lines = []
    
    for line in lines:
        # 判断是否是表格行（包含 | 且不是纯分隔线）
        is_table_line = '|' in line and not re.match(r'^[\s|:-]+$', line)
        # 判断是否是表格分隔线（如 |---|---|---|）
        is_separator_line = '|' in line and re.match(r'^[\s|:-]+$', line)
        
        if is_table_line or is_separator_line:
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


# 测试
test_text = """### 股东结构

| 股东名称 | 持股比例 | 持股数量 |
|---------|---------|---------|
| 张三 | 30% | 1656万股 |
| 李四 | 20% | 1104万股 |
| 王五 | 15% | 828万股 |
| 其他 | 35% | 1932万股 |

## 业务范围"""

tables, remaining = extract_tables(test_text)

print(f"提取到 {len(tables)} 个表格")
for i, table in enumerate(tables):
    print(f"\n表格 {i+1}:")
    print(table)

print(f"\n剩余文本:")
print(remaining)
