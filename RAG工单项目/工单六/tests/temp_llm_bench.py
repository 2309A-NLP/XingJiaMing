import os, time
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'
from dotenv import load_dotenv; load_dotenv(override=True)
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv('MIMO_API_KEY'),
    base_url=os.getenv('MIMO_BASE_URL'),
    timeout=10.0,
)

# 测试 3 次取平均
times = []
for i in range(3):
    t0 = time.time()
    resp = client.chat.completions.create(
        model='deepseek-chat',
        messages=[{'role': 'user', 'content': '你好'}],
        max_tokens=50,
    )
    t1 = time.time()
    times.append(t1 - t0)
    print(f'  Test {i+1}: {t1-t0:.2f}s')

print(f'Average: {sum(times)/len(times):.2f}s')
