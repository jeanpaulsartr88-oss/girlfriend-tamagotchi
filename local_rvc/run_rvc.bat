@echo off
chcp 65001 >nul
title Local RVC Neural Voice Server (Port 5050)
color 0b

echo ======================================================================
echo    AUTONOMOUS NEURAL RVC VOICE SERVER (C:\RVC\runtime\python.exe)
echo    Model: her_voice_200e_3400s.pth (VITS + RMVPE + HuBERT)
echo    Listening on: http://127.0.0.1:5050
echo ======================================================================
echo.

cd /d "%~dp0"

:: Освобождаем порт 5050 от любого зависшего процесса
powershell -Command "Get-NetTCPConnection -LocalPort 5050 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5050" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

set RVC_PYTHON=C:\RVC\runtime\python.exe

if not exist "%RVC_PYTHON%" (
    echo [ERROR] RVC runtime не найден по пути %RVC_PYTHON%!
    pause
    exit /b 1
)

echo [1/2] Проверка RVC Python рантайма...
"%RVC_PYTHON%" --version

echo.
echo [2/2] Запуск нейросетевого инференса на http://127.0.0.1:5050 ...
echo [INFO] Для остановки нажмите Ctrl+C.
echo.

"%RVC_PYTHON%" server.py

if errorlevel 1 (
    echo.
    echo [ERROR] Сервер остановлен с кодом ошибки %errorlevel%.
    pause
)
