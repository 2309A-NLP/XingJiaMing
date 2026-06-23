"""工单十三后端启动脚本。"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"

os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"
os.environ["PYTHONUTF8"] = "1"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def _bootstrap_venv() -> None:
    if not VENV_PYTHON.exists():
        return
    current = Path(sys.executable).resolve()
    if current == VENV_PYTHON.resolve():
        return
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), __file__])


_bootstrap_venv()

from dotenv import load_dotenv  # noqa: E402
import uvicorn  # noqa: E402

load_dotenv(override=True)


def _port_in_use(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("", port))
        return False
    except OSError:
        return True
    finally:
        sock.close()


def _free_port(port: int) -> None:
    if not _port_in_use(port):
        return

    my_pid = os.getpid()
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq python.exe", "/NH"],
        capture_output=True,
        text=True,
        errors="ignore",
    )
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].lower() == "python.exe":
            pid = int(parts[1])
            if pid != my_pid:
                print(f"清理旧进程 PID={pid}")
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)

    for _ in range(40):
        time.sleep(0.5)
        if not _port_in_use(port):
            print(f"端口 {port} 已释放")
            return
    print(f"警告: 端口 {port} 释放超时")


if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8013"))

    _free_port(port)

    print("启动工单十三 RAG 性能优化后端...")
    print(f"Python: {sys.executable}")
    print(f"地址: http://{host}:{port}")
    print(f"文档: http://{host}:{port}/docs")
    uvicorn.run("api.main:app", host=host, port=port)
