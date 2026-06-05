import os, time, json
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'
import requests

queries = [
    '你好',
    '公司的注册资本是多少？',
    '武汉力源信息技术股份有限公司本次募集资金拟投资哪些项目？',
    '公司老板是谁',
    '公司的主要客户群体有哪些？',
]

url = 'http://localhost:8005/api/query/stream'

for q in queries:
    t0 = time.time()
    r = requests.post(url, json={'question': q, 'top_k': 5, 'language': 'zh'}, timeout=30, stream=True)
    first_token = None
    answer = ''
    for line in r.iter_lines():
        if line:
            decoded = line.decode('utf-8')
            if decoded.startswith('data: '):
                data = json.loads(decoded[6:])
                if data['type'] == 'token':
                    if first_token is None:
                        first_token = time.time()
                    answer += data['data']
                if data['type'] == 'done':
                    break
    total = time.time() - t0
    ttft = first_token - t0 if first_token else 0
    mark = 'OK' if total < 3 else 'SLOW'
    print(f'[{mark}] TTFT={ttft:.1f}s Total={total:.1f}s | {q[:35]}')
    print(f'       Answer: {answer[:60]}...')
    print()
