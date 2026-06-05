@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

echo ========================================
echo   RAG QA System - Starting...
echo ========================================
echo.

echo [0/2] Cleaning up old Python processes...
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM pythonw.exe >nul 2>&1

echo Waiting for port release...
:WAIT_PORT
timeout /t 2 /nobreak >nul
netstat -ano | findstr ":8004.*LISTENING" >nul 2>&1
if %errorlevel%==0 (
    echo Port 8004 still occupied, waiting...
    goto WAIT_PORT
)
echo Port 8004 is free.

echo [1/2] Starting backend on Port 8004...
start "RAG-Backend" cmd /k "%~dp0.venv\Scripts\python.exe" run.py

echo Waiting for backend to load models...
timeout /t 40 /nobreak >nul

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