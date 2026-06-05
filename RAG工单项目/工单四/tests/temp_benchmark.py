import os, time, json
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'
import requests

queries = [
    '你好',
    '公司的注册资本是多少？',
    '公司老板是谁',
    '公司的主营业务是什么？',
    '公司面临哪些经营风险？',
]

url = 'http://localhost:8004/api/query'

for q in queries:
    t0 = time.time()
    r = requests.post(url, json={'question': q, 'top_k': 3, 'language': 'zh'}, timeout=30)
    t1 = time.time()
    result = r.json()
    elapsed = t1 - t0
    mark = 'OK' if elapsed < 3 else 'SLOW'
    print(f'[{mark}] {elapsed:.2f}s | {q[:30]}')
