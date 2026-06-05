with open(r'E:\桌面\项目文件\RAG工单项目\工单二\scripts\pipeline\chunker.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 更新 extract_tables 函数
old_func = '''def extract_tables(text: str) -> List[dict]:
    """从文本中提取表格，返回表格列表和剩余文本"""
    tables = []
    lines = text.split('\n')
    current_table = []
    in_table = False
    result_lines = []
    
    for line in lines:
        # 判断是否是表格行（包含 | 且不是纯分隔线）
        is_table_line = '|' in line and not re.match(r'^[\s|:-]+$', line)
        
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
    
    return tables, '\n'.join(result_lines)'''

new_func = '''def extract_tables(text: str) -> Tuple[List[str], str]:
    """从文本中提取表格，返回表格列表和剩余文本
    
    优化：确保表头、分隔线和数据在同一个表格块中
    """
    tables = []
    lines = text.split('\n')
    current_table = []
    in_table = False
    result_lines = []
    
    for line in lines:
        # 判断是否是表格行（包含 |）
        is_table_line = '|' in line
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
    
    return tables, '\n'.join(result_lines)'''

content = content.replace(old_func, new_func)

with open(r'E:\桌面\项目文件\RAG工单项目\工单二\scripts\pipeline\chunker.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('已更新 extract_tables 函数')
