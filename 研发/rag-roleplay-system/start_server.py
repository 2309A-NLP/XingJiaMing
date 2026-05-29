import subprocess
import sys
import os

TARGET_PORT = 8000

def get_pid_by_port(port):
    """获取指定端口的PID"""
    try:
        cmd = f"netstat -ano | findstr :{port}"
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5 and "LISTENING" in parts[3]:
                return parts[-1]
        return None
    except Exception as e:
        print(f"获取端口信息失败: {e}")
        return None

def kill_pid(pid):
    """杀死指定PID的进程"""
    try:
        subprocess.run(f"taskkill /PID {pid} /F", shell=True, capture_output=True)
        print(f"已终止进程 {pid}")
        return True
    except Exception as e:
        print(f"终止进程失败: {e}")
        return False

def start_server():
    """启动FastAPI服务"""
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    # 检查并清理端口
    pid = get_pid_by_port(TARGET_PORT)
    if pid:
        print(f"端口 {TARGET_PORT} 被进程 {pid} 占用，正在终止...")
        kill_pid(pid)
    
    # 启动服务
    from src.fastapi_app import app
    import uvicorn
    print(f"启动服务在端口 {TARGET_PORT}...")
    uvicorn.run(app, host="127.0.0.1", port=TARGET_PORT)

if __name__ == "__main__":
    start_server()