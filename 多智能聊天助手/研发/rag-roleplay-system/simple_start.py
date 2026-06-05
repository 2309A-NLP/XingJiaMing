import uvicorn
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    from src.fastapi_app import app
    
    port = 8080
    host = "127.0.0.1"  # 默认本地访问
    
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg.startswith('--port='):
                port = int(arg.split('=')[1])
            elif arg == '-p' and sys.argv.index(arg) + 1 < len(sys.argv):
                port = int(sys.argv[sys.argv.index(arg) + 1])
            elif arg == '--host=0.0.0.0' or arg == '--public':
                host = "0.0.0.0"
    
    print(f"服务启动: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)