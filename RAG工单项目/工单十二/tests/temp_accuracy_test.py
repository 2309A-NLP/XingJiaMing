import os, time, json
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'
import requests

tests = [
    ('你好', '问候语'),
    ('公司的注册资本是多少？', '应包含具体金额'),
    ('武汉力源信息技术股份有限公司本次募集资金拟投资哪些项目？', '应列出投资项目'),
    ('公司老板是谁', '应返回法定代表人或实际控制人'),
    ('文档一和文档二的区别在哪儿？', '应区分两个文档'),
]

url = 'http://localhost:8006/api/query'

print('='*60)
print(f'{"Question":<35} {"Time":>6} {"Answer Preview"}')
print('='*60)

for q, expect in tests:
    t0 = time.time()
    r = requests.post(url, json={'question': q, 'top_k': 5, 'language': 'zh'}, timeout=30)
    t1 = time.time()
    result = r.json()
    elapsed = t1 - t0
    answer = result.get('answer', '')[:50]
    mark = 'OK' if elapsed < 3 else 'SLOW'
    print(f'[{mark}] {elapsed:.1f}s | {q[:30]}')
    print(f'       Answer: {answer}...')
    print(f'       Expect: {expect}')
    print()
