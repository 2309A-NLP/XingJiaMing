#!/bin/bash
# ============================================================
# 01_server_init.sh - 阿里云 ECS 服务器初始化脚本
# 功能: 系统更新、安装基础依赖、创建用户、配置防火墙
# 适用系统: Ubuntu 22.04 LTS
# ============================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "\n${BLUE}========== $1 ==========${NC}"; }

# 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then
    log_error "请使用 root 用户运行此脚本: sudo bash $0"
    exit 1
fi

# ============================================================
# 1. 系统更新
# ============================================================
log_step "1/7 系统更新"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y
apt-get install -y curl wget git vim htop unzip software-properties-common \
    apt-transport-https ca-certificates gnupg lsb-release \
    net-tools lsof tree jq

log_info "系统更新完成"

# ============================================================
# 2. 安装 Python 3.10
# ============================================================
log_step "2/7 安装 Python 3.10"
if command -v python3.10 &>/dev/null; then
    log_info "Python 3.10 已安装: $(python3.10 --version)"
else
    apt-get install -y python3.10 python3.10-venv python3.10-dev python3-pip
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1
    log_info "Python 3.10 安装完成"
fi
python3 --version

# ============================================================
# 3. 安装 MySQL
# ============================================================
log_step "3/7 安装 MySQL"
if command -v mysql &>/dev/null; then
    log_info "MySQL 已安装: $(mysql --version)"
else
    apt-get install -y mysql-server mysql-client
    systemctl enable mysql
    systemctl start mysql
    log_info "MySQL 安装完成"

    # 初始化数据库
    MYSQL_ROOT_PWD="RagChat@2024!Secure"
    mysql -u root <<EOF
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '${MYSQL_ROOT_PWD}';
FLUSH PRIVILEGES;
CREATE DATABASE IF NOT EXISTS rag_character_chat CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'rag_user'@'%' IDENTIFIED BY 'RagUser@2024!';
GRANT ALL PRIVILEGES ON rag_character_chat.* TO 'rag_user'@'%';
FLUSH PRIVILEGES;
EOF
    log_info "MySQL 数据库初始化完成 (数据库: rag_character_chat)"
    log_warn "MySQL root 密码: ${MYSQL_ROOT_PWD}  请务必修改并妥善保管!"
fi

# ============================================================
# 4. 安装 Redis
# ============================================================
log_step "4/7 安装 Redis"
if command -v redis-server &>/dev/null; then
    log_info "Redis 已安装: $(redis-server --version)"
else
    apt-get install -y redis-server
    # 配置 Redis 以 systemd 运行
    sed -i 's/^supervised no/supervised systemd/' /etc/redis/redis.conf
    sed -i 's/^bind 127.0.0.1 ::1/bind 127.0.0.1/' /etc/redis/redis.conf
    systemctl enable redis-server
    systemctl restart redis-server
    log_info "Redis 安装完成"
fi

# ============================================================
# 5. 安装 Nginx
# ============================================================
log_step "5/7 安装 Nginx"
if command -v nginx &>/dev/null; then
    log_info "Nginx 已安装: $(nginx -v 2>&1)"
else
    apt-get install -y nginx
    systemctl enable nginx
    systemctl start nginx
    log_info "Nginx 安装完成"
fi

# ============================================================
# 6. 创建应用用户和目录
# ============================================================
log_step "6/7 创建应用用户和目录"
APP_USER="ragapp"
APP_DIR="/opt/rag-chat"

if ! id "$APP_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$APP_USER"
    usermod -aG docker "$APP_USER" 2>/dev/null || true
    log_info "用户 $APP_USER 创建完成"
else
    log_info "用户 $APP_USER 已存在"
fi

mkdir -p "$APP_DIR"/{logs,models/BAAI,backups,nginx,scripts}
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
log_info "应用目录 $APP_DIR 创建完成"

# ============================================================
# 7. 配置防火墙
# ============================================================
log_step "7/7 配置防火墙"
if command -v ufw &>/dev/null; then
    ufw allow 22/tcp    comment "SSH"
    ufw allow 80/tcp    comment "HTTP"
    ufw allow 443/tcp   comment "HTTPS"
    ufw --force enable
    log_info "防火墙配置完成 (开放: 22, 80, 443)"
else
    log_warn "ufw 未安装, 跳过防火墙配置. 请在阿里云安全组中配置端口"
fi

# 配置系统参数
cat >> /etc/sysctl.conf <<'EOF'
# RAG Chat 优化参数
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
vm.overcommit_memory = 1
vm.max_map_count = 262144
EOF
sysctl -p

# ============================================================
# 完成
# ============================================================
log_step "服务器初始化完成"
log_info "已安装: Python 3.10, MySQL, Redis, Nginx"
log_info "应用目录: $APP_DIR"
log_info "应用用户: $APP_USER"
log_warn "请记录 MySQL root 密码并修改默认密码!"
log_warn "请确保阿里云安全组已开放 22, 80, 443, 19530 端口"
