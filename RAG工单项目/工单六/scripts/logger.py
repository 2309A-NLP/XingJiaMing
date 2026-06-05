import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')


def setup_logging(level=logging.INFO):
    os.makedirs(LOG_DIR, exist_ok=True)
    fmt = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    formatter = logging.Formatter(fmt, datefmt='%Y-%m-%d %H:%M:%S')

    root = logging.getLogger()
    root.setLevel(level)

    # 清掉 uvicorn 或其他人加的 handler，统一用我们的
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    log_file = os.path.join(LOG_DIR, 'app.log')
    fh = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
    fh.setFormatter(formatter)

    root.addHandler(console)
    root.addHandler(fh)
