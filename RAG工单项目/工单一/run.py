"""工单1 - RAG问答系统后端启动脚本"""
import os
import sys

# 设置环境变量
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'
os.environ['PYTHONUTF8'] = '1'

# 确保UTF-8编码
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import uvicorn

if __name__ == '__main__':
    host = os.getenv('API_HOST', '0.0.0.0')
    port = int(os.getenv('API_PORT', '8000'))
    print(f'启动 RAG 问答系统后端...')
    print(f'地址: http://{host}:{port}')
    print(f'文档: http://{host}:{port}/docs')
    uvicorn.run("api.main:app", host=host, port=port)
