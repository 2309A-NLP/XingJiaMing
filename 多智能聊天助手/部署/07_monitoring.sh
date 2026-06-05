#!/bin/bash
# ============================================================
# 07_monitoring.sh - 系统监控配置
# 功能: 健康检查脚本、磁盘告警、日志监控、服务状态检查
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
ALERT_EMAIL="${ALERT_EMAIL:-admin@example.com}"
DISK_THRESHOLD=85

# ============================================================
# 1. 创建健康检查脚本
# ============================================================
log_step "1/4 创建健康检查脚本"

cat > "$APP_DIR/scripts/health_check.sh" <<'SCRIPT'
#!/bin/bash
# RAG 多角色对话系统 - 健康检查
set -e

APP_DIR="/opt/rag-chat"
LOG_FILE="$APP_DIR/logs/health_check.log"
ALERT_FILE="$APP_DIR/logs/alert.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"; }
alert() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ALERT] $1" | tee -a "$ALERT_FILE" "$LOG_FILE"; }

ERRORS=0

# 检查 FastAPI 服务
if curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
    log "[OK] FastAPI 服务正常"
else
    alert "[FAIL] FastAPI 服务不可用"
    ERRORS=$((ERRORS + 1))
fi

# 检查 MySQL
if mysqladmin ping -u root --silent 2>/dev/null; then
    log "[OK] MySQL 服务正常"
else
    alert "[FAIL] MySQL 服务不可用"
    ERRORS=$((ERRORS + 1))
fi

# 检查 Redis
if redis-cli ping 2>/dev/null | grep -q PONG; then
    log "[OK] Redis 服务正常"
else
    alert "[FAIL] Redis 服务不可用"
    ERRORS=$((ERRORS + 1))
fi

# 检查 Milvus
if curl -sf http://localhost:9091/healthz >/dev/null 2>&1; then
    log "[OK] Milvus 服务正常"
else
    alert "[FAIL] Milvus 服务不可用"
    ERRORS=$((ERRORS + 1))
fi

# 检查 Nginx
if systemctl is-active --quiet nginx; then
    log "[OK] Nginx 服务正常"
else
    alert "[FAIL] Nginx 服务不可用"
    ERRORS=$((ERRORS + 1))
fi

# 检查 Docker
if docker info >/dev/null 2>&1; then
    log "[OK] Docker 服务正常"
else
    alert "[FAIL] Docker 服务不可用"
    ERRORS=$((ERRORS + 1))
fi

# 检查磁盘空间
DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
if [ "$DISK_USAGE" -lt 85 ]; then
    log "[OK] 磁盘使用率: ${DISK_USAGE}%"
else
    alert "[WARN] 磁盘使用率过高: ${DISK_USAGE}%"
fi

# 检查内存
MEM_USAGE=$(free | awk '/Mem:/ {printf "%.0f", $3/$2*100}')
if [ "$MEM_USAGE" -lt 90 ]; then
    log "[OK] 内存使用率: ${MEM_USAGE}%"
else
    alert "[WARN] 内存使用率过高: ${MEM_USAGE}%"
fi

# 汇总
if [ "$ERRORS" -gt 0 ]; then
    alert "健康检查完成: ${ERRORS} 个服务异常!"
    exit 1
else
    log "健康检查完成: 所有服务正常"
    exit 0
fi
SCRIPT
chmod +x "$APP_DIR/scripts/health_check.sh"

log_info "健康检查脚本创建完成"

# ============================================================
# 2. 创建磁盘告警脚本
# ============================================================
log_step "2/4 创建磁盘告警脚本"

cat > "$APP_DIR/scripts/disk_alert.sh" <<SCRIPT
#!/bin/bash
# 磁盘空间告警
THRESHOLD=${DISK_THRESHOLD}
LOG_FILE="$APP_DIR/logs/alert.log"

USAGE=\$(df / | tail -1 | awk '{print \$5}' | tr -d '%')
if [ "\$USAGE" -ge "\$THRESHOLD" ]; then
    echo "[$(date)] [ALERT] 磁盘使用率 \${USAGE}% 超过阈值 \${THRESHOLD}%" >> "\$LOG_FILE"

    # 自动清理: 删除7天前的日志
    find "$APP_DIR/logs" -name "*.log.*" -mtime +7 -delete 2>/dev/null || true

    # 清理 Docker 无用镜像
    docker system prune -f --filter "until=168h" 2>/dev/null || true

    echo "[$(date)] [INFO] 已执行自动清理" >> "\$LOG_FILE"
fi
SCRIPT
chmod +x "$APP_DIR/scripts/disk_alert.sh"

log_info "磁盘告警脚本创建完成 (阈值: ${DISK_THRESHOLD}%)"

# ============================================================
# 3. 创建综合监控脚本
# ============================================================
log_step "3/4 创建综合监控脚本"

cat > "$APP_DIR/scripts/status.sh" <<'SCRIPT'
#!/bin/bash
# RAG 多角色对话系统 - 服务状态一览
echo "=========================================="
echo " RAG 多角色对话系统 - 服务状态"
echo " $(date)"
echo "=========================================="

echo ""
echo "--- 系统资源 ---"
echo "CPU 负载: $(uptime | awk -F'load average:' '{print $2}')"
echo "内存使用: $(free -h | awk '/Mem:/ {printf "%s / %s (%.0f%%)", $3, $2, $3/$2*100}')"
echo "磁盘使用: $(df -h / | tail -1 | awk '{printf "%s / %s (%s)", $3, $2, $5}')"

echo ""
echo "--- 服务状态 ---"
services=("rag-chat:FastAPI" "nginx:Nginx" "mysql:MySQL" "redis-server:Redis")
for svc in "${services[@]}"; do
    name="${svc%%:*}"
    label="${svc##*:}"
    if systemctl is-active --quiet "$name" 2>/dev/null; then
        echo "  ✅ $label: 运行中"
    else
        echo "  ❌ $label: 已停止"
    fi
done

# Docker 容器状态
echo ""
echo "--- Docker 容器 ---"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "  Docker 不可用"

echo ""
echo "--- 应用日志 (最近5条) ---"
tail -5 /opt/rag-chat/logs/app.log 2>/dev/null || echo "  无日志"
echo ""
SCRIPT
chmod +x "$APP_DIR/scripts/status.sh"

# ============================================================
# 4. 配置定时监控任务
# ============================================================
log_step "4/4 配置定时监控任务"

cat > /etc/cron.d/rag-chat-monitor <<EOF
# RAG 系统监控任务
# 每5分钟健康检查
*/5 * * * * root /opt/rag-chat/scripts/health_check.sh >/dev/null 2>&1

# 每小时磁盘检查
0 * * * * root /opt/rag-chat/scripts/disk_alert.sh >/dev/null 2>&1
EOF
chmod 644 /etc/cron.d/rag-chat-monitor

log_info "定时监控任务已配置"

# 立即执行一次健康检查
log_step "执行首次健康检查"
bash "$APP_DIR/scripts/health_check.sh" || true

log_step "监控配置完成"
log_info "健康检查:  每5分钟 → $APP_DIR/logs/health_check.log"
log_info "磁盘告警:  每小时 → $APP_DIR/logs/alert.log (阈值: ${DISK_THRESHOLD}%)"
log_info "手动检查:  bash $APP_DIR/scripts/health_check.sh"
log_info "状态查看:  bash $APP_DIR/scripts/status.sh"
