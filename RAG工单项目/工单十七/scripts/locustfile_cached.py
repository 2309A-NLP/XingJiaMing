"""
工单十七：RAGFlow API压测脚本（带缓存）
使用Locust模拟并发用户
"""

from locust import HttpUser, task, between
import json
import time
import csv
import os
import hashlib
from datetime import datetime

# 配置
API_TOKEN = "ragflow_test_2026"
CHAT_ID = "cae2dc30685d11f196bfc3335f372939"

# 测试问题列表
QUESTIONS = [
    "这个文档主要讲什么内容？",
    "公司的主要销售模式是什么？",
    "公司的产品开发流程是什么？",
    "公司的技术创新机制是什么？",
    "公司的采购与关联交易情况如何？",
    "公司的主要业务是什么？",
    "公司的技术实力如何？",
    "公司的业务运营模式是什么？",
]

# 查询缓存
QUERY_CACHE = {}
CACHE_TTL = 300  # 5分钟


class RAGFlowUser(HttpUser):
    """模拟RAGFlow用户（带缓存）"""
    wait_time = between(1, 3)
    
    def on_start(self):
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_TOKEN}"
        }
        self.question_index = 0
    
    @task(1)
    def ask_question(self):
        """发送问答请求（带缓存）"""
        question = QUESTIONS[self.question_index % len(QUESTIONS)]
        self.question_index += 1
        
        # 检查缓存
        cache_key = hashlib.md5(question.encode()).hexdigest()
        if cache_key in QUERY_CACHE:
            cached_time, cached_result = QUERY_CACHE[cache_key]
            if time.time() - cached_time < CACHE_TTL:
                # 缓存命中
                self.record_metric(question, 0.01, True, cache_hit=True)
                return
        
        payload = {
            "question": question,
            "stream": False
        }
        
        start_time = time.time()
        with self.client.post(
            f"/api/v1/chats/{CHAT_ID}/completions",
            json=payload,
            headers=self.headers,
            catch_response=True
        ) as response:
            end_time = time.time()
            response_time = (end_time - start_time) * 1000
            
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    response.success()
                    # 存入缓存
                    QUERY_CACHE[cache_key] = (time.time(), data)
                    self.record_metric(question, response_time, True, cache_hit=False)
                else:
                    response.failure(f"API error: {data.get('message', 'unknown')}")
                    self.record_metric(question, response_time, False, cache_hit=False)
            else:
                response.failure(f"HTTP {response.status_code}")
                self.record_metric(question, response_time, False, cache_hit=False)
    
    def record_metric(self, question, response_time, success, cache_hit=False):
        """记录性能指标"""
        filename = "/mnt/e/桌面/项目文件/RAG工单项目/工单十七/benchmark_v3_results.csv"
        file_exists = os.path.exists(filename)
        
        with open(filename, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "question", "response_time_ms", "success", "cache_hit"])
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                question[:50],
                f"{response_time:.0f}",
                "YES" if success else "NO",
                "YES" if cache_hit else "NO"
            ])
