@echo off
chcp 65001 > nul
title Starting Girlfriend Tamagotchi Full Stack
color 0e

echo ======================================================================
echo    STARTING ALL TAMAGOCHI SERVICES (VOICE SERVER + WEB SERVER)
echo ======================================================================
echo.

cd /d "%~dp0"

echo [1/2] Launching Local RVC Voice Server (Port 5050)...
start "Tamagochi Voice Server (5050)" cmd /c "cd local_rvc && run_rvc.bat"

timeout /t 2 /nobreak > nul

echo [2/2] Launching Web Server (Port 5000)...
start "Tamagochi Web Server (5000)" cmd /c "start.bat"

echo.
echo Both servers have been launched in separate windows!
echo Open your browser at: http://localhost:5000
echo (Microphone is automatically allowed on localhost!)
echo.
timeout /t 5
