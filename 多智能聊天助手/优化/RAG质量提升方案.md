# RAG质量提升方案

## RAGAS基线分析

| 指标 | 当前值 | 目标 | 差距 |
|------|--------|------|------|
| **Faithfulness** | **0.49** | **≥0.75** | **🔴 需大幅改进** |
| AnswerRelevancy | 0.83 | ≥0.90 | 🟡 小幅改进 |
| ContextPrecision | 1.00 | 保持 | ✅ |
| ContextRecall | 1.00 | 保持 | ✅ |

**关键诊断：** Context Precision/Recall均为1.0但Faithfulness仅0.49，说明：
- ✅ 检索模块工作正常（能找到正确文档）
- ❌ 生成模块没有忠实于检索到的上下文（LLM幻觉或Prompt引导不足）

---

## 提升方案

### 1. 分块Overlap实现（问题#10）

**现状：** settings配了chunk_overlap=50但chunk_text()未使用。

```python
# app/utils/text.py
def chunk_text(text: str, chunk_size: int = 512, chunk_overlap: int = 50) -> list[str]:
    """
    将文本按chunk_size分块，相邻块重叠chunk_overlap字符。
    重叠确保边界处的语义不会被切断。
    """
    if not text or not text.strip():
        return []

    text = text.strip()
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # 尝试在句号/换行处断开，避免切断句子
        if end < len(text):
            last_break = max(chunk.rfind("。"), chunk.rfind("\n"), chunk.rfind(". "))
            if last_break > chunk_size * 0.5:  # 至少保留一半长度
                chunk = chunk[:last_break + 1]
                end = start + last_break + 1

        chunks.append(chunk.strip())
        start = end - chunk_overlap  # 关键：overlap偏移

    return [c for c in chunks if c]
```

### 2. Prompt优化 — 提升Faithfulness（核心）

Faithfulness 0.49的根因是Prompt没有足够约束LLM基于上下文回答。

**现状Prompt可能过于简单：**
```python
system_prompt = f"你是{role_name}，请回答用户问题。"
user_prompt = f"参考资料：{context}\n\n问题：{question}"
```

**优化后的Prompt：**
```python
def build_rag_prompt(role_config, question: str, contexts: list[str]) -> list[dict]:
    context_block = "\n\n---\n\n".join(
        f"[参考资料{i+1}] {c}" for i, c in enumerate(contexts)
    )

    system_prompt = f"""你是{role_config.name}。

## 回答规则（必须严格遵守）

1. **忠实性优先**：你的回答必须完全基于下方提供的参考资料，不得编造、推测或添加参考资料中没有的信息。
2. **引用来源**：回答中涉及的关键事实，请标注来源，如"根据[参考资料1]..."。
3. **不确定时说明**：如果参考资料不足以回答问题，必须明确告知："根据现有资料，我无法完全回答这个问题"，然后只基于已有资料给出部分回答。
4. **拒绝幻觉**：绝对不要编造法律条文编号、医学数据、药品名称等具体信息。如果参考资料中没有，请说"资料中未提及"。
5. **角色一致性**：以{role_config.name}的专业视角回答，但不得超越参考资料的范围。

## 输出格式
- 先给出核心回答
- 如有需要，补充相关说明
- 最后注明参考依据"""

    user_prompt = f"""## 参考资料

{context_block}

## 用户问题

{question}

请严格按照上述规则回答。"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
```

### 3. 混合检索（Hybrid Search）

结合向量检索（语义匹配）和关键词检索（精确匹配），提升召回质量。

```python
# app/services/retrieval.py
from pymilvus import Collection, AnnSearchRequest, RRFRanker

def hybrid_search(query: str, collection_name: str, top_k: int = 20) -> list[dict]:
    """
    混合检索：向量相似度 + BM25关键词匹配
    使用Milvus的Hybrid Search功能
    """
    collection = Collection(collection_name)

    # 向量检索
    vector_req = AnnSearchRequest(
        data=[embed(query)],
        anns_field="embedding",
        param={"metric_type": "COSINE", "params": {"nprobe": 16}},
        limit=top_k,
    )

    # 全文检索（Milvus 2.4+ 支持）
    text_req = AnnSearchRequest(
        data=[query],
        anns_field="text_sparse",  # sparse向量字段
        param={"metric_type": "BM25"},
        limit=top_k,
    )

    # RRF融合排序
    reranker = RRFRanker(k=60)
    results = collection.hybrid_search(
        reqs=[vector_req, text_req],
        rerank=reranker,
        limit=top_k,
        output_fields=["text", "source"],
    )

    return [
        {"text": hit.entity.get("text"), "score": hit.score, "source": hit.entity.get("source")}
        for hit in results[0]
    ]
```

**如果Milvus版本不支持Hybrid Search，退化方案：**

```python
def hybrid_search_fallback(query, collection, top_k=20):
    # 向量检索
    vec_results = vector_search(query, collection, top_k=top_k)
    # 关键词过滤（MySQL LIKE / Elasticsearch）
    kw_results = keyword_search(query, top_k=top_k)

    # RRF融合
    return reciprocal_rank_fusion([vec_results, kw_results], k=60)
```

### 4. Reranker调优

```python
# 当前可能的rerank调用
def rerank(query, candidates, top_k=5):
    return reranker.rerank(query, candidates, top_k=top_k)

# 优化：增加候选数 + 过滤低分结果
def rerank_optimized(query, candidates, top_k=5, min_score=0.3):
    # 先rerank更多候选
    reranked = reranker.rerank(query, candidates, top_k=top_k * 2)
    # 过滤低于阈值的
    filtered = [r for r in reranked if r["score"] >= min_score]
    # 取top_k
    return filtered[:top_k]
```

### 5. 上下文窗口优化

```python
def build_context(contexts: list[str], max_tokens: int = 3000) -> str:
    """
    控制上下文长度，避免过长导致LLM注意力分散。
    优先保留高相关性（排在前面的）片段。
    """
    total = 0
    selected = []
    for ctx in contexts:
        token_est = len(ctx) // 2  # 粗略估算：2字符≈1token
        if total + token_est > max_tokens:
            break
        selected.append(ctx)
        total += token_est
    return "\n\n---\n\n".join(selected)
```

### 6. RAGAS评估自动化

```python
# scripts/eval_ragas.py
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
from datasets import Dataset

# 准备评估数据集
eval_data = {
    "question": [
        "什么是合同违约？",
        "感冒发烧怎么办？",
        "如何缓解焦虑情绪？",
        # ... 至少20条
    ],
    "answer": [],       # 从系统获取
    "contexts": [],     # 从检索模块获取
    "ground_truth": [], # 人工标注的标准答案
}

# 运行评估
dataset = Dataset.from_dict(eval_data)
result = evaluate(
    dataset,
    metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
)
print(result)
# {'faithfulness': 0.75, 'answer_relevancy': 0.90, ...}
```

**集成到CI：**
```yaml
# .github/workflows/eval.yml
- name: Run RAGAS evaluation
  run: python scripts/eval_ragas.py
- name: Check thresholds
  run: |
    python -c "
    import json
    r = json.load(open('eval_result.json'))
    assert r['faithfulness'] >= 0.75, f'Faithfulness {r[\"faithfulness\"]} < 0.75'
    assert r['answer_relevancy'] >= 0.85, f'AnswerRelevancy {r[\"answer_relevancy\"]} < 0.85'
    "
```

---

## 预期效果

| 优化项 | Faithfulness影响 | AnswerRelevancy影响 |
|--------|-----------------|-------------------|
| Prompt约束加强 | +0.15~0.20 | +0.03 |
| chunk_overlap实现 | +0.05 | +0.02 |
| 混合检索 | +0.03 | +0.03 |
| Reranker调优 | +0.02 | +0.02 |
| **合计预估** | **0.49→0.74~0.79** | **0.83→0.93** |
