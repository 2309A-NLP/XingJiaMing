"""工单4 - RAG问答系统后端启动脚本"""
import os
import sys
import socket
import time
from pathlib import Path
from subprocess import run as sp_run

# 设置环境变量
os.environ['NO_PROXY'] = 'localhost,127.0.0.1'
os.environ['no_proxy'] = 'localhost,127.0.0.1'
os.environ['PYTHONUTF8'] = '1'

# 项目根目录
_project_root = Path(__file__).parent

# 确保UTF-8编码
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(override=True)

import uvicorn


def _port_in_use(port: int) -> bool:
    """检测端口是否被占用"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('', port))
        sock.close()
        return False
    except OSError:
        return True
    finally:
        sock.close()


def _free_port(port: int) -> None:
    """杀掉占用端口的进程，等端口释放后再返回"""
    if not _port_in_use(port):
        return

    # 杀掉所有 python.exe 进程（自己除外）
    my_pid = os.getpid()
    result = sp_run(['tasklist', '/FI', 'IMAGENAME eq python.exe', '/NH'],
                    capture_output=True, text=True, errors='ignore')
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == 'python.exe':
            pid = int(parts[1])
            if pid != my_pid:
                print(f'杀掉旧进程 PID={pid}')
                sp_run(['taskkill', '/F', '/PID', str(pid)], capture_output=True)

    # 等端口释放，最多等 20 秒
    for i in range(40):
        time.sleep(0.5)
        if not _port_in_use(port):
            print(f'端口 {port} 已释放')
            return
    print(f'警告: 端口 {port} 释放超时')


if __name__ == '__main__':
    host = os.getenv('API_HOST', '0.0.0.0')
    port = int(os.getenv('API_PORT', '8000'))

    _free_port(port)

    print(f'启动 RAG 问答系统后端...')
    print(f'地址: http://{host}:{port}')
    print(f'文档: http://{host}:{port}/docs')
    uvicorn.run("api.main:app", host=host, port=port)