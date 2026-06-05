@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

echo ========================================
echo   RAG QA System - Starting...
echo ========================================
echo.

echo [1/2] Starting backend...
start "RAG-Backend" cmd /k "cd /d "%~dp0" && ".venv\Scripts\python.exe" run.py"

timeout /t 2 /nobreak >nul

echo [2/2] Starting frontend...
cd /d "%~dp0frontend"
start "RAG-Frontend" cmd /k "npx vite --host"

timeout /t 5 /nobreak >nul

echo.
echo ========================================
echo   All started!
echo   Open: http://localhost:5173
echo ========================================
echo.
echo Press any key to close this window...
pause >nul