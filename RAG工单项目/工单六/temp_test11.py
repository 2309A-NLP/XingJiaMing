import requests
import os

os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)

url = "http://localhost:8006/api/query"
data = {
    "question": "公司的主营业务是什么",
    "top_k": 3,
    "language": "zh",
    "search_mode": "hybrid",
    "vector_weight": 1.0,
    "bm25_weight": 1.5,
    "rerank_enabled": True,
    "reranker_type": "tfidf"
}

try:
    response = requests.post(url, json=data, timeout=30, proxies={"http": None, "https": None})
    print(f"API 响应状态: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"API 调用成功")
        print(f"  回答长度: {len(result.get('answer', ''))} 字符")
        print(f"  来源数量: {len(result.get('sources', []))} 条")
    else:
        print(f"API 调用失败: {response.text[:300]}")
except Exception as e:
    print(f"错误: {e}")
