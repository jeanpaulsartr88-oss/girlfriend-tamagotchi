@echo off
chcp 65001 >nul
title Local RVC Voice Inference Server (Port 5050)
color 0b

echo ======================================================================
echo    STARTING AUTONOMOUS LOCAL RVC VOICE SERVER FOR GIRLFRIEND-TAMAGOTCHI
echo ======================================================================
echo.

cd /d "%~dp0"

:: Free port 5050 if an old hanging instance exists
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5050" ^| findstr "LISTENING"') do (
    echo Freeing port 5050 from previous instance (PID %%a)...
    taskkill /F /PID %%a >nul 2>&1
)

echo [1/3] Checking Python environment...
python --version
if errorlevel 1 (
    echo [ERROR] Python not found in PATH!
    pause
    exit /b 1
)

echo.
echo [2/3] Checking Model Assets in %CD%...
if exist "model.pth" (
    echo   [OK] Model weights found: model.pth
) else (
    echo   [WARN] model.pth not found!
)

if exist "model.index" (
    echo   [OK] FAISS index found: model.index
) else (
    echo   [WARN] model.index not found.
)

echo.
echo [3/3] Launching Voice Microservice on http://127.0.0.1:5050 ...
echo Press Ctrl+C to stop the voice server.
echo.

python server.py

if errorlevel 1 (
    echo.
    echo [ERROR] Voice server stopped with error code %errorlevel%.
    pause
)
