#!/bin/bash
# ============================================================
# 04_nginx_setup.sh - Nginx 反向代理配置
# 功能: 配置反向代理、静态文件、gzip 压缩、安全头、限流
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

APP_DIR="/opt/rag-chat"
NGINX_CONF="/etc/nginx/sites-available/rag-chat"
NGINX_LINK="/etc/nginx/sites-enabled/rag-chat"
SERVER_NAME="${SERVER_NAME:-120.26.32.90}"

# ============================================================
# 1. 创建 Nginx 配置
# ============================================================
log_step "1/3 创建 Nginx 配置"

# 备份默认配置
if [ -f /etc/nginx/sites-enabled/default ]; then
    rm -f /etc/nginx/sites-enabled/default
    log_info "已移除默认站点配置"
fi

cat > "$NGINX_CONF" <<NGINX
# === RAG 多角色对话系统 Nginx 配置 ===
# 生成时间: $(date)

# 限流配置
limit_req_zone \$binary_remote_addr zone=api_limit:10m rate=30r/s;
limit_req_zone \$binary_remote_addr zone=chat_limit:10m rate=10r/s;

# 上游服务
upstream rag_backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name ${SERVER_NAME};

    # --- 安全头 ---
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:;" always;

    # --- Gzip 压缩 ---
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_min_length 1024;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript image/svg+xml;

    # --- 请求体大小限制 (上传文件等) ---
    client_max_body_size 50m;

    # --- 静态文件 ---
    location /static/ {
        alias ${APP_DIR}/static/;
        expires 7d;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # --- 前端资源 ---
    location /assets/ {
        alias ${APP_DIR}/static/assets/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # --- API 限流 ---
    location /api/chat/ {
        limit_req zone=chat_limit burst=20 nodelay;
        limit_req_status 429;

        proxy_pass http://rag_backend;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Connection "";

        # SSE (Server-Sent Events) 流式响应支持
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    # --- API 反向代理 ---
    location /api/ {
        limit_req zone=api_limit burst=50 nodelay;

        proxy_pass http://rag_backend;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Connection "";
        proxy_read_timeout 60s;
    }

    # --- WebSocket 支持 (如有需要) ---
    location /ws/ {
        proxy_pass http://rag_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 86400s;
    }

    # --- 主路由 (前端页面) ---
    location / {
        proxy_pass http://rag_backend;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Connection "";
    }

    # --- 健康检查 ---
    location /health {
        proxy_pass http://rag_backend/api/health;
        access_log off;
    }

    # --- 禁止访问隐藏文件 ---
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }

    # --- 日志 ---
    access_log /var/log/nginx/rag-chat-access.log;
    error_log /var/log/nginx/rag-chat-error.log warn;
}
NGINX

log_info "Nginx 配置文件生成完成: $NGINX_CONF"

# ============================================================
# 2. 启用配置
# ============================================================
log_step "2/3 启用站点配置"
ln -sf "$NGINX_CONF" "$NGINX_LINK"

# 复制配置到项目目录供参考
mkdir -p "$APP_DIR/nginx"
cp "$NGINX_CONF" "$APP_DIR/nginx/rag-roleplay.conf"
chown -R ragapp:ragapp "$APP_DIR/nginx"

# ============================================================
# 3. 测试并重载 Nginx
# ============================================================
log_step "3/3 测试并重载 Nginx"
nginx -t
systemctl reload nginx

if systemctl is-active --quiet nginx; then
    log_info "Nginx 配置生效, 服务运行正常"
else
    log_error "Nginx 启动失败"
    systemctl status nginx --no-pager
    exit 1
fi

log_step "Nginx 配置完成"
log_info "站点配置: $NGINX_CONF"
log_info "访问地址: http://${SERVER_NAME}"
log_warn "如需配置 SSL, 请运行 05_ssl_setup.sh"
