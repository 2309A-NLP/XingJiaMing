import os, sys, time
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv(override=True)

from api.init import get_components
from api.routes.query import _is_simple_query

comp = get_components()

# 复杂查询（会触发 Query Understanding）
query = '武汉力源信息技术股份有限公司本次募集资金拟投资哪些项目？'
print(f'Query: {query}')
print(f'is_simple: {_is_simple_query(query)}')

# 通过 API 测试完整流程
import requests
t0 = time.time()
r = requests.post('http://localhost:8005/api/query/stream', 
    json={'question': query, 'top_k': 5, 'language': 'zh'}, 
    timeout=30, stream=True)

first_token_time = None
last_token_time = None
for line in r.iter_lines():
    if line:
        decoded = line.decode('utf-8')
        if decoded.startswith('data: '):
            import json
            data = json.loads(decoded[6:])
            if data['type'] == 'token' and first_token_time is None:
                first_token_time = time.time()
            if data['type'] == 'token':
                last_token_time = time.time()
            if data['type'] == 'done':
                break

total = time.time() - t0
ttft = first_token_time - t0 if first_token_time else 0
print(f'Time to first token: {ttft:.2f}s')
print(f'Total time: {total:.2f}s')
