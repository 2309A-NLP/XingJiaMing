import os, sys, time
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv(override=True)

from api.init import get_components

comp = get_components()
embedder = comp['embedder']
store = comp['store']
bm25 = comp['bm25']
retriever = comp['retriever']
generator = comp['generator']

query = '公司的注册资本是多少？'

# 1. Embedding
t0 = time.time()
query_vec = embedder.encode([query])[0]
t_embed = time.time() - t0
print(f'1. Embedding:     {t_embed:.2f}s')

# 2. Vector search
t0 = time.time()
dense = store.search(query_vec, top_k=15)
t_vec = time.time() - t0
print(f'2. Vector search: {t_vec:.2f}s')

# 3. BM25
t0 = time.time()
sparse = bm25.search(query, top_k=20)
t_bm25 = time.time() - t0
print(f'3. BM25 search:   {t_bm25:.2f}s')

# 4. RRF merge
t0 = time.time()
merged = retriever._merge(dense, sparse)
t_rrf = time.time() - t0
print(f'4. RRF merge:     {t_rrf:.3f}s')

# 5. Rerank (if available)
if retriever._reranker:
    t0 = time.time()
    reranked = retriever._reranker.rerank(query, merged[:16], top_k=10)
    t_rerank = time.time() - t0
    print(f'5. Rerank:        {t_rerank:.2f}s')
else:
    print(f'5. Rerank:        skipped')

# 6. LLM generation (with context)
from api.routes.query import _build_context_from_results
contexts = _build_context_from_results(merged[:10])
t0 = time.time()
answer = generator.generate(query, contexts)
t_llm = time.time() - t0
print(f'6. LLM generate:  {t_llm:.2f}s')

total = t_embed + t_vec + t_bm25 + t_rrf + t_llm
print(f'---')
print(f'Total:            {total:.2f}s')
