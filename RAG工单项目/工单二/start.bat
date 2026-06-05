@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

echo ========================================
echo   RAG QA System - Starting...
echo ========================================
echo.

echo [1/2] Starting backend on port 8002...
start "RAG-Backend" cmd /k "%~dp0.venv\Scripts\python.exe" run.py

echo Waiting for backend to load models...
timeout /t 30 /nobreak >nul

echo [2/2] Starting frontend...
cd /d "%~dp0frontend"
start "RAG-Frontend" cmd /k npx vite --host

timeout /t 5 /nobreak >nul

echo.
echo ========================================
echo   All started!
echo   Open: http://localhost:5173
echo ========================================
echo.
pause