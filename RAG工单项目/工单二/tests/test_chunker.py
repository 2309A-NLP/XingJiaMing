import sys
sys.path.insert(0, r'E:\桌面\项目文件\RAG工单项目\工单二')

from scripts.pipeline.chunker import Chunker

# 测试文本
test_md = """
# 公司概况

武汉兴图新科电子股份有限公司是一家专注于视频通信领域的高科技公司。

## 注册资本

公司的注册资本是 **5,520 万元**。这个数字在 2018 年 8 月增资后确定下来，之后没有再变化过。

### 股东结构

| 股东名称 | 持股比例 | 持股数量 |
|---------|---------|---------|
| 张三 | 30% | 1656万股 |
| 李四 | 20% | 1104万股 |
| 王五 | 15% | 828万股 |
| 其他 | 35% | 1932万股 |

## 业务范围

公司主要从事以下业务：
1. 视频通信系统研发
2. 智能视频分析
3. 军用视频指挥系统
4. 民用视频会议系统

公司在军用领域具有较强的技术优势，是多个军工项目的视频通信系统供应商。
"""

chunker = Chunker(max_chars=600, overlap=50, min_chars=30)
parents, children = chunker.chunk(test_md)

print(f"父块数量: {len(parents)}")
print(f"子块数量: {len(children)}")
print()

for i, child in enumerate(children):
    is_table = child.metadata.get('is_table', False)
    print(f"子块 {i+1} ({'表格' if is_table else '正文'}):")
    print(f"  长度: {len(child.content)} 字符")
    print(f"  内容: {child.content[:100]}...")
    print()
