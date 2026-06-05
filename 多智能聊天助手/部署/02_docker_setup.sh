#!/bin/bash
# ============================================================
# 02_docker_setup.sh - Docker 安装 + Milvus 集群启动
# 功能: 安装 Docker/Docker Compose, 启动 Milvus (etcd+minio+milvus)
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

# ============================================================
# 1. 安装 Docker
# ============================================================
log_step "1/3 安装 Docker"
if command -v docker &>/dev/null; then
    log_info "Docker 已安装: $(docker --version)"
else
    curl -fsSL https://get.docker.com | bash
    systemctl enable docker
    systemctl start docker
    log_info "Docker 安装完成"
fi

# 安装 Docker Compose (v2 插件)
if ! docker compose version &>/dev/null; then
    mkdir -p /usr/local/lib/docker/cli-plugins
    COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep tag_name | cut -d '"' -f 4)
    curl -SL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
        -o /usr/local/lib/docker/cli-plugins/docker-compose
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
    log_info "Docker Compose 安装完成"
else
    log_info "Docker Compose 已安装: $(docker compose version)"
fi

# 将 ragapp 用户加入 docker 组
usermod -aG docker ragapp 2>/dev/null || true

# ============================================================
# 2. 生成 Milvus Docker Compose 文件
# ============================================================
log_step "2/3 生成 Milvus Docker Compose 配置"
COMPOSE_FILE="$APP_DIR/docker-compose.yml"

if [ -f "$COMPOSE_FILE" ]; then
    log_warn "docker-compose.yml 已存在, 备份后重新生成"
    cp "$COMPOSE_FILE" "${COMPOSE_FILE}.bak.$(date +%Y%m%d%H%M%S)"
fi

cat > "$COMPOSE_FILE" <<'YAML'
version: '3.5'
services:
  etcd:
    image: quay.io/coreos/etcd:v3.5.5
    container_name: milvus-etcd
    environment:
      ETCD_AUTO_COMPACTION_MODE: revision
      ETCD_AUTO_COMPACTION_RETENTION: '1000'
      ETCD_QUOTA_BACKEND_BYTES: '4294967296'
      ETCD_SNAPSHOT_COUNT: '50000'
    volumes:
      - etcd:/etcd
    command: etcd -advertise-client-urls=http://127.0.0.1:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd
    healthcheck:
      test: ["CMD", "etcdctl", "endpoint", "health"]
      interval: 30s
      timeout: 20s
      retries: 3
    restart: always

  minio:
    image: minio/minio:RELEASE.2023-03-20T20-16-18Z
    container_name: milvus-minio
    environment:
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
    volumes:
      - minio_data:/minio_data
    command: minio server /minio_data --console-address ':9001'
    ports:
      - '9000:9000'
      - '9001:9001'
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3
    restart: always

  milvus-standalone:
    image: milvusdb/milvus:v2.4.5
    container_name: milvus-standalone
    command: ['milvus', 'run', 'standalone']
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
    volumes:
      - milvus_data:/var/lib/milvus
    ports:
      - '19530:19530'
      - '9091:9091'
    depends_on:
      etcd:
        condition: service_healthy
      minio:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
      interval: 30s
      timeout: 20s
      retries: 3
    restart: always

volumes:
  etcd:
  minio_data:
  milvus_data:
YAML

chown ragapp:ragapp "$COMPOSE_FILE"
log_info "docker-compose.yml 已生成"

# ============================================================
# 3. 启动 Milvus 集群
# ============================================================
log_step "3/3 启动 Milvus 集群"
cd "$APP_DIR"
docker compose up -d

log_info "等待 Milvus 启动..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:9091/healthz >/dev/null 2>&1; then
        log_info "Milvus 启动成功! (端口: 19530, 耗时约 ${i}0秒)"
        break
    fi
    sleep 10
    if [ "$i" -eq 30 ]; then
        log_error "Milvus 启动超时, 请检查日志: docker compose -f $COMPOSE_FILE logs"
        exit 1
    fi
done

docker compose ps

log_step "Docker & Milvus 部署完成"
log_info "Milvus:       localhost:19530"
log_info "MinIO:        localhost:9001 (admin: minioadmin/minioadmin)"
log_info "Milvus健康检查: localhost:9091/healthz"
