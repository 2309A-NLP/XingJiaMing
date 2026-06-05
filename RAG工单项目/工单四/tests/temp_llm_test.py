import os, time
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'
from dotenv import load_dotenv; load_dotenv(override=True)
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv('MIMO_API_KEY'),
    base_url=os.getenv('MIMO_BASE_URL'),
)

# 测试 1: 简单问候
t0 = time.time()
resp = client.chat.completions.create(
    model='deepseek-chat',
    messages=[{'role': 'user', 'content': '你好'}],
    max_tokens=50,
)
t1 = time.time()
print(f'Simple query: {t1-t0:.2f}s')
print(f'Answer: {resp.choices[0].message.content}')

# 测试 2: 带上下文的问答
t0 = time.time()
resp = client.chat.completions.create(
    model='deepseek-chat',
    messages=[
        {'role': 'system', 'content': '你是文档助手，根据参考资料回答。'},
        {'role': 'user', 'content': '参考资料：公司注册资本5000万元。\n\n问题：注册资本是多少？'}
    ],
    max_tokens=200,
)
t1 = time.time()
print(f'RAG query: {t1-t0:.2f}s')
print(f'Answer: {resp.choices[0].message.content}')
