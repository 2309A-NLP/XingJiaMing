# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
import unittest
import random

# 模拟重排序函数（请替换为你实际的 rerank 逻辑）
def rerank(items, query=None, top_k=10):
    """
    示例重排序函数：按简单规则打乱/排序后返回 top_k 结果
    :param items: 待排序的列表（如 [(item1, score1), (item2, score2), ...]）
    :param query: 检索查询词（可选）
    :param top_k: 返回前 k 个结果
    :return: 重排序后的列表
    """
    if not items:
        return []
    # 示例逻辑：按分数降序排序（你可替换为实际的 rerank 算法，如交叉编码、BM25 等）
    sorted_items = sorted(items, key=lambda x: x[1], reverse=True)
    return sorted_items[:top_k]

# 测试用例
class TestRerank(unittest.TestCase):
    def setUp(self):
        # 初始化测试数据
        self.test_items = [
            ("item1", 0.2),
            ("item2", 0.8),
            ("item3", 0.5),
            ("item4", 0.9),
            ("item5", 0.1)
        ]
        self.empty_items = []

    def test_rerank_basic(self):
        """测试基础重排序功能"""
        result = rerank(self.test_items, top_k=3)
        # 验证返回数量
        self.assertEqual(len(result), 3)
        # 验证排序逻辑（最高分在前）
        self.assertEqual(result[0][0], "item4")  # 0.9 最高分
        self.assertEqual(result[1][0], "item2")  # 0.8 次高分

    def test_rerank_empty_input(self):
        """测试空输入的边界情况"""
        result = rerank(self.empty_items)
        self.assertEqual(result, [])

    def test_rerank_top_k_exceed_length(self):
        """测试 top_k 超过输入长度的情况"""
        result = rerank(self.test_items, top_k=10)
        self.assertEqual(len(result), len(self.test_items))  # 返回全部数据

    def test_rerank_with_query(self):
        """测试带查询词的重排序（可扩展自定义逻辑）"""
        # 若你的 rerank 依赖 query，可在此补充测试逻辑
        result = rerank(self.test_items, query="test_query", top_k=2)
        self.assertEqual(len(result), 2)

if __name__ == '__main__':
    # 运行所有测试用例
    unittest.main(verbosity=2)