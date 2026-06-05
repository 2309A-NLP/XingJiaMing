import os, time
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'
import requests

t0 = time.time()
r = requests.post('http://localhost:8004/api/query', 
    json={'question': '公司老板是谁', 'top_k': 3}, timeout=30)
t1 = time.time()
print(f'Total: {t1-t0:.2f}s')
print(f'Status: {r.status_code}')
