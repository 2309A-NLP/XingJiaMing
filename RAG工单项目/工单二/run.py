"""工单2 - RAG问答系统后端启动脚本"""
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
    """检测端口是否被占用（绑定 0.0.0.0，和 uvicorn 保持一致）"""
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
    """检测端口是否被占用，占用则自动杀掉对应进程，等端口释放后再返回"""
    if not _port_in_use(port):
        return

    # 通过 netstat 找到占用端口的 PID
    result = sp_run(['netstat', '-ano'], capture_output=True, text=True, errors='ignore')
    for line in result.stdout.splitlines():
        if f':{port}' in line and 'LISTENING' in line:
            pid = line.strip().split()[-1]
            print(f'端口 {port} 被进程 PID={pid} 占用，正在清理...')
            sp_run(['taskkill', '/F', '/PID', pid], capture_output=True)
            break
    else:
        print(f'警告: 端口 {port} 被占用但未找到对应进程，请手动检查')
        return

    # 等端口真正释放，最多等 5 秒
    for i in range(10):
        time.sleep(0.5)
        if not _port_in_use(port):
            print(f'端口 {port} 已释放')
            return
    print(f'警告: 端口 {port} 释放超时，尝试继续启动')


if __name__ == '__main__':
    host = os.getenv('API_HOST', '0.0.0.0')
    port = int(os.getenv('API_PORT', '8000'))

    _free_port(port)

    print(f'启动 RAG 问答系统后端...')
    print(f'地址: http://{host}:{port}')
    print(f'文档: http://{host}:{port}/docs')
    uvicorn.run("api.main:app", host=host, port=port)
