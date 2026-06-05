import sys
sys.path.insert(0, r"E:\桌面\项目文件\RAG工单项目\工单六")

# 测试重排器工厂函数
from scripts.pipeline.reranker import create_reranker, TFIDFReranker, LLMReranker, AdaptiveReranker

# 测试 TF-IDF 重排器
print("=== 测试 TF-IDF 重排器 ===")
tfidf = TFIDFReranker()
print(f"名称: {tfidf.name}")

# 模拟候选结果
candidates = [
    {"chunk_id": "1", "content": "公司的主营业务是人工智能技术研发"},
    {"chunk_id": "2", "content": "公司成立于2020年，注册资本1000万"},
    {"chunk_id": "3", "content": "公司主要客户群体包括政府和企业"},
]

results = tfidf.rerank("公司的主营业务是什么", candidates, top_k=2)
print(f"重排结果: {len(results)} 条")
for r in results:
    print(f"  - {r['chunk_id']}: {r['content'][:30]}... (分数: {r.get('rerank_score', 0):.4f})")

# 测试 LLM 重排器
print("\n=== 测试 LLM 重排器 ===")
llm = LLMReranker()
print(f"名称: {llm.name}")

# 测试自适应重排器
print("\n=== 测试自适应重排器 ===")
adaptive = AdaptiveReranker(tfidf_reranker=tfidf)
print(f"名称: {adaptive.name}")

# 测试工厂函数
print("\n=== 测试工厂函数 ===")
for reranker_type in ["bge", "llm", "tfidf", "adaptive"]:
    try:
        reranker = create_reranker(reranker_type=reranker_type)
        print(f"✓ {reranker_type}: {reranker.name}")
    except Exception as e:
        print(f"✗ {reranker_type}: {e}")

print("\n=== 测试完成 ===")
