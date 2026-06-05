import sys
sys.path.insert(0, r'E:\桌面\项目文件\RAG工单项目\工单二')

from scripts.pipeline.chunker import Chunker

# 测试更复杂的文本
test_md = """
# 公司概况

武汉兴图新科电子股份有限公司是一家专注于视频通信领域的高科技公司。公司成立于2005年，总部位于武汉东湖高新技术开发区。

## 注册资本

公司的注册资本是 **5,520 万元**。这个数字在 2018 年 8 月增资后确定下来，之后没有再变化过。公司于2018年完成了股份制改造，注册资本由原来的3000万元增加到5520万元。

### 股东结构

| 股东名称 | 持股比例 | 持股数量 |
|---------|---------|---------|
| 张三 | 30% | 1656万股 |
| 李四 | 20% | 1104万股 |
| 王五 | 15% | 828万股 |
| 其他 | 35% | 1932万股 |

## 业务范围

公司主要从事以下业务：
1. 视频通信系统研发：公司拥有自主知识产权的视频编解码技术
2. 智能视频分析：基于深度学习的视频内容分析系统
3. 军用视频指挥系统：为军队提供安全可靠的视频指挥解决方案
4. 民用视频会议系统：面向企业和政府的高清视频会议系统

公司在军用领域具有较强的技术优势，是多个军工项目的视频通信系统供应商。报告期内，公司来自军用领域的收入占比超过80%。
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
    print(f"  内容预览: {child.content[:80]}...")
    print()
