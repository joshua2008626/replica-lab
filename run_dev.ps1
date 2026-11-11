# REPLICA LAB - PowerShell Development Launcher
$ErrorActionPreference = "Stop"

Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host "                REPLICA LAB - AI Software Intelligence Studio                  " -ForegroundColor Cyan
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$BackendDir = Join-Path $ScriptDir "backend"
$FrontendDir = Join-Path $ScriptDir "frontend"
$PythonExe = Join-Path $BackendDir "venv\Scripts\python.exe"

# 1. Check Python virtual environment
if (-not (Test-Path $PythonExe)) {
    Write-Host "[ERROR] Backend virtual environment not found at $PythonExe" -ForegroundColor Red
    Write-Host "Please set up the backend virtual environment first:" -ForegroundColor Yellow
    Write-Host "  cd $BackendDir; python -m venv venv; .\venv\Scripts\pip install -r requirements.txt"
    exit 1
}

# 2. Check Frontend node_modules
$NodeModules = Join-Path $FrontendDir "node_modules"
if (-not (Test-Path $NodeModules)) {
    Write-Host "[WARNING] frontend/node_modules not found. Running npm install..." -ForegroundColor Yellow
    Start-Process -FilePath "npm.cmd" -ArgumentList "install" -WorkingDirectory $FrontendDir -Wait -NoNewWindow
}

Write-Host "[1/2] Starting FastAPI Backend on http://127.0.0.1:8000 ..." -ForegroundColor Green
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "cd /d `"$BackendDir`" && venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

Write-Host "[2/2] Starting Vite Frontend on http://localhost:5173 ..." -ForegroundColor Green
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "cd /d `"$FrontendDir`" && npm.cmd run dev"

Start-Sleep -Seconds 3
Start-Process "http://localhost:5173"

Write-Host ""
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host " Services launched successfully:" -ForegroundColor Green
Write-Host "  - Frontend Studio: http://localhost:5173" -ForegroundColor White
Write-Host "  - Backend API:     http://127.0.0.1:8000" -ForegroundColor White
Write-Host "  - API Swagger Doc: http://127.0.0.1:8000/docs" -ForegroundColor White
Write-Host "===============================================================================" -ForegroundColor Cyan
