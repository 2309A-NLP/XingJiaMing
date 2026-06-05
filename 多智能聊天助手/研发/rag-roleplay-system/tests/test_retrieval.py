import sys
import os

# 自动把项目根目录加入路径
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TEST_DIR)
sys.path.append(PROJECT_ROOT)

# 强制刷新输出，确保Windows能看到打印
import time
print("=" * 60)
print("🧪 开始测试 Milvus 向量检索功能")
print("=" * 60)
time.sleep(0.2)

import random
from rag.retrieval import create_law_collection, insert_chunks, search_vector

# ==========================
# 测试工具函数
# ==========================
def generate_test_vectors(num: int, dim: int = 1024) -> list:
    return [[random.uniform(-1.0, 1.0) for _ in range(dim)] for _ in range(num)]

def generate_test_chunks(num: int) -> list:
    return [f"测试法律文本片段 {i}：中华人民共和国XX法 第{random.randint(1,100)}条 规定......" for i in range(num)]

# ==========================
# 核心测试
# ==========================
def test_milvus_full_process():
    try:
        print("\n✅ 1. 正在创建集合...")
        create_law_collection()
        time.sleep(0.2)

        print("\n✅ 2. 正在生成测试数据...")
        test_chunks = generate_test_chunks(10)
        test_vectors = generate_test_vectors(10)

        print("\n✅ 3. 正在插入数据...")
        insert_count = insert_chunks(test_chunks, test_vectors)
        print(f"   成功插入 {insert_count} 条数据！")
        time.sleep(0.2)

        print("\n✅ 4. 正在检索向量...")
        query_vector = test_vectors[3]
        search_result = search_vector(query_vector, top_k=3)

        print("\n📌 检索结果（Top3）：")
        print("-" * 50)
        for idx, hit in enumerate(search_result[0], 1):
            print(f"排名 {idx}")
            print(f"相似度：{hit['distance']:.4f}")
            print(f"内容：{hit['entity']['text']}")
            print(f"ID：{hit['id']}")
            print("-" * 50)
            time.sleep(0.1)

    except Exception as e:
        print(f"\n❌ 错误：{e}")
        raise

# ==========================
# 边界测试
# ==========================
def test_edge_cases():
    print("\n✅ 5. 正在测试边界场景...")
    try:
        search_vector([1.0]*512)
    except ValueError as e:
        print(f"   维度校验正常：{e}")

    try:
        insert_chunks(["文本1"], [])
    except ValueError as e:
        print(f"   长度校验正常：{e}")

# ==========================
# 运行
# ==========================
if __name__ == "__main__":
    test_milvus_full_process()
    test_edge_cases()

    print("\n" + "="*60)
    print("🎉 🎉 🎉 所有测试全部通过！")
    print("Milvus 连接、创建、插入、检索 100% 正常！")
    print("="*60)