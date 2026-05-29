#!/bin/bash
# ============================================================
# 05_ssl_setup.sh - Let's Encrypt SSL 证书安装
# 功能: 安装 certbot, 申请 SSL 证书, 配置自动续期
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

DOMAIN="${1:-}"
EMAIL="${2:-admin@example.com}"

if [ -z "$DOMAIN" ]; then
    log_error "用法: $0 <域名> [邮箱]"
    log_error "示例: $0 rag-chat.example.com admin@example.com"
    log_error "注意: 域名必须已解析到本服务器 IP"
    exit 1
fi

# ============================================================
# 1. 安装 Certbot
# ============================================================
log_step "1/4 安装 Certbot"
if command -v certbot &>/dev/null; then
    log_info "Certbot 已安装"
else
    apt-get install -y certbot python3-certbot-nginx
    log_info "Certbot 安装完成"
fi

# ============================================================
# 2. 更新 Nginx 配置中的域名
# ============================================================
log_step "2/4 更新 Nginx 域名配置"
NGINX_CONF="/etc/nginx/sites-available/rag-chat"

if [ -f "$NGINX_CONF" ]; then
    sed -i "s/server_name .*/server_name ${DOMAIN};/" "$NGINX_CONF"
    nginx -t && systemctl reload nginx
    log_info "Nginx 域名已更新为: $DOMAIN"
else
    log_error "Nginx 配置不存在: $NGINX_CONF"
    log_error "请先运行 04_nginx_setup.sh"
    exit 1
fi

# ============================================================
# 3. 申请 SSL 证书
# ============================================================
log_step "3/4 申请 SSL 证书"
certbot --nginx \
    -d "$DOMAIN" \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    --redirect

log_info "SSL 证书申请成功"

# ============================================================
# 4. 配置自动续期
# ============================================================
log_step "4/4 配置自动续期"

# 创建续期钩子: 续期后自动重载 Nginx
cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<'HOOK'
#!/bin/bash
systemctl reload nginx
HOOK
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

# 测试续期
certbot renew --dry-run

# 确保定时任务存在
CRON_LINE="0 3 * * * certbot renew --quiet --deploy-hook 'systemctl reload nginx'"
(crontab -l 2>/dev/null | grep -v certbot; echo "$CRON_LINE") | crontab -
log_info "自动续期已配置 (每天凌晨3点检查)"

log_step "SSL 配置完成"
log_info "HTTPS 地址: https://${DOMAIN}"
log_info "证书路径: /etc/letsencrypt/live/${DOMAIN}/"
log_info "自动续期: 每天凌晨 3:00 检查"
log_warn "请确保防火墙/安全组已开放 443 端口"
