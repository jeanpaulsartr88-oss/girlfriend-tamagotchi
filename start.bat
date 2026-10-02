@echo off
chcp 65001 > nul
echo ========================================================
echo   💖 Запуск Тамагочи Любимой (Telegram Mini App)
echo ========================================================
echo.
echo Открытие сайта в браузере: http://localhost:8000
start http://localhost:8000
echo.
echo Запуск локального сервера FastAPI...
python main.py
pause
