@echo off
chcp 65001 > nul
title Tamagochi Lelya Web Server (HTTPS / Port 5000)
color 0a

echo ======================================================================
echo    STARTING TAMAGOCHI SERVER IN HTTPS SECURE MODE (PORT 5000)
echo ======================================================================
echo.

cd /d "%~dp0"

:: Free port 5000 if an old hanging instance exists
powershell -Command "Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

set USE_SSL=true
python app.py
if errorlevel 1 (
    echo.
    echo [ERROR] Web server stopped with error code %errorlevel%.
    pause
)
