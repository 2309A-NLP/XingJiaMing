import os, sys, time
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv(override=True)

from api.init import get_components

comp = get_components()

query = '公司老板是谁'

# 1. Embedding
t0 = time.time()
query_vec = comp['embedder'].encode([query])[0]
t1 = time.time()
print(f'Embedding: {t1-t0:.2f}s')

# 2. Retrieval (parallel)
from concurrent.futures import ThreadPoolExecutor
t2 = time.time()
with ThreadPoolExecutor(max_workers=2) as ex:
    dense = ex.submit(comp['store'].search, query_vec, 9).result()
    sparse = ex.submit(comp['bm25'].search, query, 12).result()
t3 = time.time()
print(f'Retrieval: {t3-t2:.2f}s')

# 3. RRF
merged = comp['retriever']._merge(dense, sparse)
t4 = time.time()
print(f'RRF: {t4-t3:.3f}s')

# 4. LLM (streaming)
from api.routes.query import _build_context_from_results
contexts = _build_context_from_results(merged[:3])
t5 = time.time()
answer = ''
for token in comp['generator'].generate_stream(query, contexts):
    if not answer:
        t6 = time.time()
        print(f'TTFT (after context build): {t6-t5:.2f}s')
    answer += token
t7 = time.time()
print(f'LLM total: {t7-t5:.2f}s')
print(f'---')
print(f'Total: {t7-t0:.2f}s')
print(f'Answer: {answer[:80]}')
