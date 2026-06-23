#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAG客户端 - 调用本地RAG API获取金融知识回答
"""

import requests
import time

# 配置
RAG_API_URL = 'https://herself-ferment-accustom.ngrok-free.dev'
HEADERS = {'ngrok-skip-browser-warning': 'true'}

def query_rag(question, strategy='hybrid'):
    """
    调用RAG API获取回答
    
    Args:
        question: 用户问题
        strategy: 检索策略 (hybrid/vector/bm25)
    
    Returns:
        RAG回答文本
    """
    url = f'{RAG_API_URL}/api/query'
    data = {
        'question': question,
        'strategy': strategy
    }
    
    try:
        start = time.time()
        response = requests.post(url, json=data, headers=HEADERS, timeout=30)
        response.raise_for_status()
        result = response.json()
        elapsed = time.time() - start
        
        answer = result.get('answer', 'RAG未返回有效回答。')
        print(f'RAG响应时间: {elapsed:.2f}秒')
        
        return answer
    except requests.exceptions.Timeout:
        return 'RAG请求超时，请稍后重试。'
    except requests.exceptions.ConnectionError:
        return '无法连接到RAG服务，请检查本地RAG和ngrok是否运行。'
    except Exception as e:
        return f'RAG调用出错: {str(e)}'

def test_rag():
    """测试RAG API"""
    test_questions = [
        '你好',
        '这两家公司的主要业务是什么？',
        '招股说明书中提到的主要风险因素有哪些？',
        '公司的注册资本是多少？'
    ]
    
    print('=== RAG API测试 ===\n')
    
    for question in test_questions:
        print(f'问题: {question}')
        answer = query_rag(question)
        print(f'回答: {answer[:100]}...')
        print('-' * 50)

if __name__ == '__main__':
    test_rag()
