# RAG 金融问答系统 - Backend Dockerfile
# 精简版：不装build-essential，依赖全部用wheel
# 配置国内镜像源（阿里云apt + 清华pip）

FROM python:3.10-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUTF8=1

# 换阿里云 apt 源 —— 兼容 DEB822 格式（python:3.10-slim 基于 Debian trixie）
RUN find /etc/apt -name '*.sources' -exec sed -i 's|deb.debian.org|mirrors.aliyun.com|g' {} + && \
    find /etc/apt -name '*.sources' -exec sed -i 's|security.debian.org|mirrors.aliyun.com/debian-security|g' {} +

# 只装 curl（healthcheck用）
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# 配置 pip 清华源
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

# 复制本地 PyTorch CPU wheel
COPY torch-2.5.1+cpu-cp310-cp310-linux_x86_64.whl /tmp/
COPY torchvision-0.20.1+cpu-cp310-cp310-linux_x86_64.whl /tmp/

# 装 PyTorch（本地wheel）+ 其他依赖
COPY requirements.txt .
RUN pip install --no-cache-dir 'pip<25' && \
    pip install --no-cache-dir jinja2 typing-extensions sympy networkx filelock && \
    pip install --no-cache-dir --no-deps /tmp/torch-2.5.1+cpu-cp310-cp310-linux_x86_64.whl && \
    pip install --no-cache-dir --no-deps /tmp/torchvision-0.20.1+cpu-cp310-cp310-linux_x86_64.whl && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -f /tmp/*.whl

# 复制应用代码
COPY api/ ./api/
COPY scripts/ ./scripts/
COPY run_docker.py .
COPY .env .env

RUN mkdir -p /app/data /app/storage /app/logs

EXPOSE 8007

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8007/api/health || exit 1

CMD ["python", "run_docker.py"]
