#!/bin/bash
# ============================================================
# rollback.sh - 回滚脚本
# 功能: 回滚应用到指定版本、恢复配置、恢复数据库
# 用法: sudo bash rollback.sh [选项]
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

APP_DIR="/opt/rag-chat"
BACKUP_DIR="$APP_DIR/backups"

if [ "$EUID" -ne 0 ]; then
    log_error "请使用 root 用户运行此脚本"
    exit 1
fi

show_menu() {
    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║    RAG 多角色对话系统 - 回滚工具    ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
    echo ""
    echo "  1) 回滚应用代码 (git reset)"
    echo "  2) 恢复 MySQL 数据库"
    echo "  3) 恢复 Milvus 数据"
    echo "  4) 恢复环境配置 (.env)"
    echo "  5) 回滚 Nginx 配置"
    echo "  6) 完整回滚 (代码+数据库+配置)"
    echo "  7) 查看备份列表"
    echo "  0) 退出"
    echo ""
    read -p "请选择操作 [0-7]: " CHOICE
}

# 列出备份文件
list_backups() {
    local dir="$1"
    local pattern="$2"
    log_step "可用备份 ($dir)"
    if [ -d "$dir" ]; then
        ls -lht "$dir"/$pattern 2>/dev/null | head -20 || echo "  无备份文件"
    else
        echo "  备份目录不存在"
    fi
}

# 回滚代码
rollback_code() {
    log_step "回滚应用代码"
    cd "$APP_DIR"

    echo "Git 提交历史 (最近10条):"
    sudo -u ragapp git log --oneline -10
    echo ""
    read -p "输入要回滚到的 commit hash (留空取消): " COMMIT

    if [ -z "$COMMIT" ]; then
        log_info "已取消"
        return
    fi

    # 停止服务
    systemctl stop rag-chat

    # 回滚代码
    sudo -u ragapp git reset --hard "$COMMIT"

    # 重新安装依赖
    sudo -u ragapp bash -c "
        source $APP_DIR/venv/bin/activate
        pip install -r requirements.txt -q
    "

    # 重启服务
    systemctl start rag-chat
    log_info "代码已回滚到 $COMMIT"
}

# 恢复 MySQL
restore_mysql() {
    log_step "恢复 MySQL 数据库"
    list_backups "$BACKUP_DIR/mysql" "*.sql.gz"

    read -p "输入备份文件完整路径 (留空取消): " FILE
    if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
        log_info "已取消或文件不存在"
        return
    fi

    source "$APP_DIR/.env"

    log_warn "即将覆盖数据库 ${MYSQL_DATABASE}, 当前数据将丢失!"
    read -p "确认恢复? (y/N): " CONFIRM
    if [ "$CONFIRM" != "y" ]; then
        log_info "已取消"
        return
    fi

    # 恢复
    gunzip -c "$FILE" | mysql -u"${MYSQL_USER}" -p"${MYSQL_PASSWORD}" "${MYSQL_DATABASE}"
    log_info "MySQL 数据库已恢复: $FILE"
}

# 恢复 Milvus
restore_milvus() {
    log_step "恢复 Milvus 数据"
    list_backups "$BACKUP_DIR/milvus" "*.tar.gz"

    read -p "输入备份文件完整路径 (留空取消): " FILE
    if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
        log_info "已取消或文件不存在"
        return
    fi

    log_warn "即将覆盖 Milvus 数据!"
    read -p "确认恢复? (y/N): " CONFIRM
    if [ "$CONFIRM" != "y" ]; then
        log_info "已取消"
        return
    fi

    cd "$APP_DIR"
    docker compose stop milvus-standalone
    docker run --rm \
        -v milvus_data:/milvus_data \
        -v "$(dirname "$FILE")":/backup \
        alpine sh -c "rm -rf /milvus_data/* && tar xzf /backup/$(basename "$FILE") -C /milvus_data"
    docker compose start milvus-standalone

    log_info "Milvus 数据已恢复: $FILE"
}

# 恢复配置
restore_env() {
    log_step "恢复环境配置"
    list_backups "$APP_DIR" ".env.bak.*"

    read -p "输入备份文件完整路径 (留空取消): " FILE
    if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
        log_info "已取消或文件不存在"
        return
    fi

    cp "$FILE" "$APP_DIR/.env"
    chown ragapp:ragapp "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    systemctl restart rag-chat

    log_info "环境配置已恢复: $FILE"
}

# 回滚 Nginx
rollback_nginx() {
    log_step "回滚 Nginx 配置"
    NGINX_BACKUP="/etc/nginx/sites-available/rag-chat.bak"

    if [ -f "$NGINX_BACKUP" ]; then
        cp "$NGINX_BACKUP" /etc/nginx/sites-available/rag-chat
        nginx -t && systemctl reload nginx
        log_info "Nginx 配置已回滚"
    else
        log_warn "未找到 Nginx 备份配置"
    fi
}

# 完整回滚
full_rollback() {
    log_step "完整回滚"
    log_warn "此操作将回滚: 代码 + 数据库 + 配置"
    read -p "确认完整回滚? (y/N): " CONFIRM
    if [ "$CONFIRM" != "y" ]; then
        log_info "已取消"
        return
    fi

    rollback_code
    restore_mysql
    restore_env
    rollback_nginx

    log_info "完整回滚完成"
}

# 主循环
while true; do
    show_menu
    case "$CHOICE" in
        1) rollback_code ;;
        2) restore_mysql ;;
        3) restore_milvus ;;
        4) restore_env ;;
        5) rollback_nginx ;;
        6) full_rollback ;;
        7)
            list_backups "$BACKUP_DIR/mysql" "*.sql.gz"
            list_backups "$BACKUP_DIR/milvus" "*.tar.gz"
            list_backups "$BACKUP_DIR/app" "*.tar.gz"
            list_backups "$APP_DIR" ".env.bak.*"
            ;;
        0) log_info "已退出"; exit 0 ;;
        *) log_error "无效选项" ;;
    esac
done
