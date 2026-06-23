@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   RAG QA System - Starting...
echo ========================================
echo.

echo [1/2] Starting backend + Docker (WSL)...
start "Backend" wsl -e bash "/mnt/e/桌面/项目文件/RAG工单项目/工单十二/start_wsl.sh"

echo [2/2] Starting frontend (Port 5173)...
timeout /t 3 /nobreak >nul
cd frontend
start "Frontend" cmd /k "npx vite --host"
cd ..

echo.
echo ========================================
echo   All started! Open: http://localhost:5173
echo ========================================
pause
