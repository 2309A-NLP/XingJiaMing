#!/bin/bash
# 数据库每日备份脚本
# 用法: bash scripts/backup_db.sh
# cron: 0 3 * * * /bin/bash /root/rag-project/scripts/backup_db.sh

BACKUP_DIR="/root/rag-project/backups"
DB_NAME="rag_character_chat"
DB_USER="root"
DB_PASS="Xjm@123456"
RETENTION_DAYS=30

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.sql.gz"

mysqldump -u"$DB_USER" -p"$DB_PASS" --single-transaction --routines --triggers "$DB_NAME" | gzip > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    echo "[$(date)] 备份成功: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
else
    echo "[$(date)] 备份失败!"
    exit 1
fi

# 清理过期备份
find "$BACKUP_DIR" -name "${DB_NAME}_*.sql.gz" -mtime +$RETENTION_DAYS -delete
echo "[$(date)] 已清理 ${RETENTION_DAYS} 天前的旧备份"
