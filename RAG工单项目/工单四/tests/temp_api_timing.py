import os, sys, time
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv(override=True)

from api.init import get_components
comp = get_components()

# 测试完整 API 流程
import requests
t0 = time.time()
r = requests.post('http://localhost:8004/api/query', 
    json={'question': '公司老板是谁', 'top_k': 3}, timeout=30)
t1 = time.time()
result = r.json()
print(f'API total: {t1-t0:.2f}s')
print(f'Answer: {result["answer"][:80]}')
