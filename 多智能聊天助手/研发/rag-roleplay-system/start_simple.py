import subprocess
import sys

if __name__ == "__main__":
    sys.path.insert(0, '.')
    from src.fastapi_app import app
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)