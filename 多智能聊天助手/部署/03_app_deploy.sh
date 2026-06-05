#!/bin/bash
# ============================================================
# 03_app_deploy.sh - 应用部署脚本
# 功能: 克隆代码、创建虚拟环境、安装依赖、下载模型、配置环境变量、创建 systemd 服务
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "\n${BLUE}========== $1 ==========${NC}"; }

if [ "$EUID" -ne 0 ]; then
    log_error "请使用 root 用户运行此脚本"
    exit 1
fi

# 配置变量 (请根据实际情况修改)
APP_DIR="/opt/rag-chat"
APP_USER="ragapp"
GIT_REPO="${GIT_REPO:-https://github.com/your-org/rag-character-chat.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"
DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-your-api-key-here}"

# ============================================================
# 1. 克隆代码
# ============================================================
log_step "1/6 克隆应用代码"
if [ -d "$APP_DIR/.git" ]; then
    log_info "代码已存在, 执行 git pull"
    cd "$APP_DIR"
    sudo -u "$APP_USER" git pull origin "$GIT_BRANCH"
else
    log_info "从 $GIT_REPO 克隆代码 (分支: $GIT_BRANCH)"
    sudo -u "$APP_USER" git clone -b "$GIT_BRANCH" "$GIT_REPO" "$APP_DIR"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
log_info "代码更新完成"

# ============================================================
# 2. 创建 Python 虚拟环境并安装依赖
# ============================================================
log_step "2/6 创建虚拟环境并安装依赖"
cd "$APP_DIR"

if [ ! -d "venv" ]; then
    sudo -u "$APP_USER" python3.10 -m venv venv
    log_info "虚拟环境创建完成"
fi

# 安装依赖
sudo -u "$APP_USER" bash -c "
    source venv/bin/activate
    pip install --upgrade pip setuptools wheel
    if [ -f requirements.txt ]; then
        pip install -r requirements.txt
    else
        log_warn 'requirements.txt 不存在, 跳过依赖安装'
    fi
"
log_info "依赖安装完成"

# ============================================================
# 3. 下载 AI 模型
# ============================================================
log_step "3/6 下载 AI 模型 (BGE-M3 + BGE-Reranker-Base)"
MODEL_DIR="$APP_DIR/models/BAAI"
mkdir -p "$MODEL_DIR"
chown -R "$APP_USER:$APP_USER" "$APP_DIR/models"

# 安装 huggingface-hub CLI
sudo -u "$APP_USER" bash -c "
    source $APP_DIR/venv/bin/activate
    pip install huggingface-hub -q
"

# 下载 BGE-M3
if [ -d "$MODEL_DIR/bge-m3" ] && [ -f "$MODEL_DIR/bge-m3/config.json" ]; then
    log_info "BGE-M3 模型已存在, 跳过下载"
else
    log_info "下载 BGE-M3 模型 (~2.2GB)..."
    sudo -u "$APP_USER" bash -c "
        source $APP_DIR/venv/bin/activate
        python -c \"
from huggingface_hub import snapshot_download
snapshot_download('BAAI/bge-m3', local_dir='$MODEL_DIR/bge-m3', resume_download=True)
\"
    "
    log_info "BGE-M3 下载完成"
fi

# 下载 BGE-Reranker-Base
if [ -d "$MODEL_DIR/bge-reranker-base" ] && [ -f "$MODEL_DIR/bge-reranker-base/config.json" ]; then
    log_info "BGE-Reranker-Base 模型已存在, 跳过下载"
else
    log_info "下载 BGE-Reranker-Base 模型 (~1.1GB)..."
    sudo -u "$APP_USER" bash -c "
        source $APP_DIR/venv/bin/activate
        python -c \"
from huggingface_hub import snapshot_download
snapshot_download('BAAI/bge-reranker-base', local_dir='$MODEL_DIR/bge-reranker-base', resume_download=True)
\"
    "
    log_info "BGE-Reranker-Base 下载完成"
fi

# ============================================================
# 4. 配置环境变量
# ============================================================
log_step "4/6 配置环境变量"
ENV_FILE="$APP_DIR/.env"

if [ -f "$ENV_FILE" ]; then
    log_warn ".env 已存在, 备份后重新生成"
    cp "$ENV_FILE" "${ENV_FILE}.bak.$(date +%Y%m%d%H%M%S)"
fi

# 生成随机 JWT 密钥
JWT_SECRET=$(openssl rand -hex 32)

# 从现有配置读取 MySQL 密码
MYSQL_PWD=$(grep -oP 'MYSQL_PASSWORD=\K.*' "$ENV_FILE" 2>/dev/null || echo "RagChat@2024!Secure")

cat > "$ENV_FILE" <<EOF
# === RAG 多角色对话系统环境配置 ===
# 生成时间: $(date)

# JWT 认证
JWT_SECRET=${JWT_SECRET}

# DeepSeek API
DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
DEEPSEEK_API_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v4-flash

# MySQL 数据库
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=${MYSQL_PWD}
MYSQL_DATABASE=rag_character_chat

# Redis 缓存
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0

# Milvus 向量数据库
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530
EOF

chown "$APP_USER:$APP_USER" "$ENV_FILE"
chmod 600 "$ENV_FILE"
log_info ".env 配置完成 (JWT密钥已自动生成)"

# ============================================================
# 5. 创建 systemd 服务
# ============================================================
log_step "5/6 创建 systemd 服务"
cat > /etc/systemd/system/rag-chat.service <<EOF
[Unit]
Description=RAG Multi-Role Dialogue System
After=network.target mysql.service redis-server.service
Wants=mysql.service redis-server.service

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2 --log-level info
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=5
StandardOutput=append:$APP_DIR/logs/app.log
StandardError=append:$APP_DIR/logs/app_error.log

# 安全限制
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$APP_DIR

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable rag-chat
log_info "systemd 服务创建完成"

# ============================================================
# 6. 启动应用
# ============================================================
log_step "6/6 启动应用"
systemctl restart rag-chat
sleep 3

if systemctl is-active --quiet rag-chat; then
    log_info "应用启动成功!"
    systemctl status rag-chat --no-pager -l
else
    log_error "应用启动失败, 请检查日志:"
    log_error "  journalctl -u rag-chat -n 50 --no-pager"
    log_error "  cat $APP_DIR/logs/app_error.log"
    exit 1
fi

log_step "应用部署完成"
log_info "应用地址: http://localhost:8000"
log_info "日志目录: $APP_DIR/logs/"
log_info "环境配置: $APP_DIR/.env"
log_warn "请检查 DEEPSEEK_API_KEY 是否已正确配置!"
