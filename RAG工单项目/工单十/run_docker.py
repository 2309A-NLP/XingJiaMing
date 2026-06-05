"""RAG 金融问答系统 - Docker 版启动脚本

去除 Windows 特定代码，适用于 Linux/Docker 环境
"""
import os
import sys
import logging
from pathlib import Path

# 设置环境变量
os.environ.setdefault('NO_PROXY', '*')
os.environ.setdefault('PYTHONUTF8', '1')

# 加载 .env 文件
from dotenv import load_dotenv
load_dotenv(override=True)

logger = logging.getLogger(__name__)


def main() -> None:
    """主函数"""
    import uvicorn

    # 从环境变量读取配置
    host = os.getenv('API_HOST', '0.0.0.0')
    port = int(os.getenv('API_PORT', '8007'))

    # 确保必要目录存在
    Path('./data').mkdir(exist_ok=True)
    Path('./storage').mkdir(exist_ok=True)
    Path('./logs').mkdir(exist_ok=True)

    logger.info("=" * 50)
    logger.info("  RAG 金融问答系统 - Docker 版")
    logger.info("=" * 50)
    logger.info(f"  地址: http://{host}:{port}")
    logger.info(f"  文档: http://{host}:{port}/docs")
    logger.info("=" * 50)

    # 启动 uvicorn
    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    main()
