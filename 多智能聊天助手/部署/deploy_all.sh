#!/bin/bash
# ============================================================
# deploy_all.sh - 一键部署主脚本
# 功能: 按顺序执行所有部署步骤
# 用法: sudo bash deploy_all.sh [--domain your.domain.com] [--email admin@example.com]
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "\n${CYAN}╔══════════════════════════════════════════╗${NC}"; echo -e "${CYAN}║  $1${NC}"; echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOMAIN=""
EMAIL=""

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --domain) DOMAIN="$2"; shift 2 ;;
        --email)  EMAIL="$2"; shift 2 ;;
        *)        log_error "未知参数: $1"; exit 1 ;;
    esac
done

if [ "$EUID" -ne 0 ]; then
    log_error "请使用 root 用户运行: sudo bash $0"
    exit 1
fi

echo -e "${CYAN}"
cat << 'ASCII'
 ____      _    ____ _     ___ _   _  ____
|  _ \    / \  / ___| |   |_ _| \ | |/ ___|
| |_) |  / _ \| |   | |    | ||  \| | |
|  _ <  / ___ \ |___| |___ | || |\  | |___
|_| \_\/_/   \_\____|_____|___|_| \_|\____|

   多角色智能问答系统 - 一键部署
ASCII
echo -e "${NC}"

log_warn "此脚本将执行完整的服务器部署流程"
log_warn "预计耗时: 15-30 分钟 (取决于网络速度)"
echo ""
read -p "确认开始部署? (y/N): " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    log_info "部署已取消"
    exit 0
fi

START_TIME=$(date +%s)

# ============================================================
# Step 1: 服务器初始化
# ============================================================
log_step "Step 1/7 - 服务器初始化"
bash "$SCRIPT_DIR/01_server_init.sh"

# ============================================================
# Step 2: Docker & Milvus
# ============================================================
log_step "Step 2/7 - Docker & Milvus 部署"
bash "$SCRIPT_DIR/02_docker_setup.sh"

# ============================================================
# Step 3: 应用部署
# ============================================================
log_step "Step 3/7 - 应用部署"
bash "$SCRIPT_DIR/03_app_deploy.sh"

# ============================================================
# Step 4: Nginx 配置
# ============================================================
log_step "Step 4/7 - Nginx 反向代理配置"
export SERVER_NAME="${DOMAIN:-120.26.32.90}"
bash "$SCRIPT_DIR/04_nginx_setup.sh"

# ============================================================
# Step 5: SSL 证书 (仅在指定域名时)
# ============================================================
if [ -n "$DOMAIN" ]; then
    log_step "Step 5/7 - SSL 证书配置"
    bash "$SCRIPT_DIR/05_ssl_setup.sh" "$DOMAIN" "${EMAIL:-admin@example.com}"
else
    log_step "Step 5/7 - SSL 证书 (跳过 - 未指定域名)"
    log_warn "如需 SSL, 请运行: sudo bash 05_ssl_setup.sh your.domain.com"
fi

# ============================================================
# Step 6: 备份配置
# ============================================================
log_step "Step 6/7 - 自动备份配置"
bash "$SCRIPT_DIR/06_backup_setup.sh"

# ============================================================
# Step 7: 监控配置
# ============================================================
log_step "Step 7/7 - 监控配置"
bash "$SCRIPT_DIR/07_monitoring.sh"

# ============================================================
# 完成
# ============================================================
END_TIME=$(date +%s)
DURATION=$(( (END_TIME - START_TIME) / 60 ))

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║             🎉 部署完成! 耗时: ${DURATION} 分钟              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BLUE}应用地址:${NC}  http://${SERVER_NAME}"
[ -n "$DOMAIN" ] && echo -e "  ${BLUE}HTTPS:${NC}     https://${DOMAIN}"
echo -e "  ${BLUE}API 文档:${NC}  http://${SERVER_NAME}/docs"
echo -e "  ${BLUE}Milvus:${NC}    http://${SERVER_NAME}:9001"
echo ""
echo -e "  ${YELLOW}管理命令:${NC}"
echo -e "    状态查看:  bash /opt/rag-chat/scripts/status.sh"
echo -e "    健康检查:  bash /opt/rag-chat/scripts/health_check.sh"
echo -e "    手动备份:  bash /opt/rag-chat/scripts/backup_all.sh"
echo -e "    查看日志:  tail -f /opt/rag-chat/logs/app.log"
echo -e "    服务管理:  systemctl [start|stop|restart|status] rag-chat"
echo ""
echo -e "  ${RED}注意事项:${NC}"
echo -e "    1. 请检查 .env 中的 DEEPSEEK_API_KEY 是否正确"
echo -e "    2. 请修改默认的 MySQL 密码"
echo -e "    3. 建议配置域名并启用 SSL (05_ssl_setup.sh)"
echo ""
