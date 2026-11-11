@echo off
title REPLICA LAB - Development Launcher
color 0b

echo ===============================================================================
echo                 REPLICA LAB - AI Software Intelligence Studio
echo ===============================================================================
echo.
echo [1/2] Launching FastAPI Backend on http://127.0.0.1:8000 ...
start "REPLICA LAB Backend (FastAPI :8000)" cmd /k "cd /d "%~dp0backend" && venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

echo [2/2] Launching React 19 Frontend on http://localhost:5173 ...
start "REPLICA LAB Frontend (Vite :5173)" cmd /k "cd /d "%~dp0frontend" && npm.cmd run dev"

timeout /t 3 /nobreak >nul
start http://localhost:5173

echo.
echo ===============================================================================
echo  Services launched in separate windows:
echo   - Backend API:  http://127.0.0.1:8000 (Docs: http://127.0.0.1:8000/docs)
echo   - Frontend App: http://localhost:5173
echo.
echo  Press any key to close this launcher window (services will stay running).
echo ===============================================================================
pause >nul
