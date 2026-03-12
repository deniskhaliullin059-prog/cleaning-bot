@echo off
echo ========================================
echo   ООО ВИД — Запуск системы
echo ========================================

cd /d "%~dp0"

:: Выбрать python из venv или системный
set PYTHON=python
if exist venv\Scripts\python.exe (
    set PYTHON=venv\Scripts\python.exe
)

echo Используется: %PYTHON%
echo.

:: Установить зависимости
%PYTHON% -m pip install flask requests --quiet

echo [1/2] Запуск Telegram-бота...
start "ООО ВИД — Бот" cmd /k "%PYTHON% bot.py"

timeout /t 2 /nobreak > nul

echo [2/2] Запуск веб-интерфейса...
start "ООО ВИД — Веб" cmd /k "%PYTHON% app.py"

timeout /t 4 /nobreak > nul

echo.
echo ========================================
echo  Система запущена!
echo  Веб-интерфейс: http://localhost:5000
echo ========================================
echo.

start http://localhost:5000

pause
