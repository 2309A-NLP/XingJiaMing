import sys
sys.path.insert(0, r'E:\桌面\项目文件\RAG工单项目\工单二')

from scripts.pipeline.chunker import extract_tables

# 测试表格提取
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
