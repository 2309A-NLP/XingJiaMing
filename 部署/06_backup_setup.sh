#!/bin/bash
# ============================================================
# 06_backup_setup.sh - 自动备份配置
# 功能: MySQL 备份、Milvus 数据备份、定时任务、备份清理
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
BACKUP_DIR="$APP_DIR/backups"
RETENTION_DAYS=7
MYSQL_PWD=$(grep -oP 'MYSQL_PASSWORD=\K.*' "$APP_DIR/.env" 2>/dev/null || echo "")

# ============================================================
# 1. 创建备份脚本
# ============================================================
log_step "1/3 创建备份脚本"
mkdir -p "$BACKUP_DIR"/{mysql,milvus,app}

# MySQL 备份脚本
cat > "$APP_DIR/scripts/backup_mysql.sh" <<'SCRIPT'
#!/bin/bash
set -e
BACKUP_DIR="/opt/rag-chat/backups/mysql"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/rag_character_chat_${DATE}.sql.gz"
RETENTION_DAYS=7

source /opt/rag-chat/.env

echo "[$(date)] 开始 MySQL 备份..."
mysqldump -u"${MYSQL_USER}" -p"${MYSQL_PASSWORD}" \
    --single-transaction --routines --triggers \
    "${MYSQL_DATABASE}" | gzip > "$BACKUP_FILE"

echo "[$(date)] MySQL 备份完成: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

# 清理过期备份
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +${RETENTION_DAYS} -delete
echo "[$(date)] 已清理 ${RETENTION_DAYS} 天前的备份"
SCRIPT
chmod +x "$APP_DIR/scripts/backup_mysql.sh"

# Milvus 备份脚本
cat > "$APP_DIR/scripts/backup_milvus.sh" <<'SCRIPT'
#!/bin/bash
set -e
BACKUP_DIR="/opt/rag-chat/backups/milvus"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7

echo "[$(date)] 开始 Milvus 数据备份..."
cd /opt/rag-chat

# 停止 Milvus 后备份数据卷
docker compose stop milvus-standalone
docker run --rm \
    -v milvus_data:/milvus_data \
    -v "$BACKUP_DIR":/backup \
    alpine tar czf "/backup/milvus_data_${DATE}.tar.gz" -C /milvus_data .
docker compose start milvus-standalone

echo "[$(date)] Milvus 备份完成: milvus_data_${DATE}.tar.gz"

# 清理过期备份
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +${RETENTION_DAYS} -delete
SCRIPT
chmod +x "$APP_DIR/scripts/backup_milvus.sh"

# 综合备份脚本
cat > "$APP_DIR/scripts/backup_all.sh" <<'SCRIPT'
#!/bin/bash
set -e
echo "========== 全量备份开始: $(date) =========="
/opt/rag-chat/scripts/backup_mysql.sh
/opt/rag-chat/scripts/backup_milvus.sh

# 备份配置文件
tar czf /opt/rag-chat/backups/app/config_$(date +%Y%m%d_%H%M%S).tar.gz \
    -C /opt/rag-chat .env docker-compose.yml nginx/ 2>/dev/null || true

echo "========== 全量备份完成: $(date) =========="
SCRIPT
chmod +x "$APP_DIR/scripts/backup_all.sh"

log_info "备份脚本创建完成"

# ============================================================
# 2. 创建日志轮转配置
# ============================================================
log_step "2/3 配置日志轮转"
cat > /etc/logrotate.d/rag-chat <<EOF
${APP_DIR}/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 640 ragapp ragapp
    sharedscripts
    postrotate
        systemctl reload rag-chat > /dev/null 2>&1 || true
    endscript
}
EOF
log_info "日志轮转配置完成 (保留14天)"

# ============================================================
# 3. 配置定时任务
# ============================================================
log_step "3/3 配置定时任务"
CRON_FILE="/etc/cron.d/rag-chat-backup"

cat > "$CRON_FILE" <<EOF
# RAG 多角色对话系统 - 自动备份
# 每天凌晨 2:00 执行 MySQL 备份
0 2 * * * root /opt/rag-chat/scripts/backup_mysql.sh >> /opt/rag-chat/logs/backup.log 2>&1

# 每周日凌晨 4:00 执行 Milvus 全量备份
0 4 * * 0 root /opt/rag-chat/scripts/backup_milvus.sh >> /opt/rag-chat/logs/backup.log 2>&1

# 每月1日执行全量备份
0 1 1 * * root /opt/rag-chat/scripts/backup_all.sh >> /opt/rag-chat/logs/backup.log 2>&1
EOF
chmod 644 "$CRON_FILE"
log_info "定时备份任务已配置"

log_step "备份配置完成"
log_info "MySQL 备份:  每天 02:00 → $BACKUP_DIR/mysql/"
log_info "Milvus 备份: 每周日 04:00 → $BACKUP_DIR/milvus/"
log_info "全量备份:    每月1日 01:00 → $BACKUP_DIR/"
log_info "备份保留:    ${RETENTION_DAYS} 天"
log_info "手动备份:    bash $APP_DIR/scripts/backup_all.sh"
