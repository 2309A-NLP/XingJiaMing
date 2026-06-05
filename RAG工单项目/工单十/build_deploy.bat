@echo off
cd /d "E:\桌面\项目文件\RAG工单项目\工单十"
set DOCKER_BUILDKIT=0
set COMPOSE_DOCKER_CLI_BUILD=0
docker compose up --build -d
pause
