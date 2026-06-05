# 测试embedding
import sys
import os

# 把项目根目录加入Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rag.embedding import embed_query, embed_texts

# 测试单个查询
query = "打人打成轻伤会怎么样？"
query_embedding = embed_query(query)
print(f"单个查询向量: {query_embedding[:5]}")  # 打印前5个维度的向量

# 测试批量文本
texts = [
    "第232条 故意杀人罪……",
    "第233条 过失致人死亡罪……",
    "第234条 故意伤害罪……"
]
batch_embeddings = embed_texts(texts)
print(f"批量文本向量: {batch_embeddings.shape}")  # 打印向量的维度，应该是 (批次数, 向量维度)