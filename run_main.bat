@echo off
setlocal

REM Change to the folder where main.py is located
cd /d "C:\Automation\1_5EMA_100Volume\5EMA_100Volume"

REM If you have a virtual environment, activate it (optional)
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

REM Run the Python script
py "C:\Automation\1_5EMA_100Volume\5EMA_100Volume\main.py"

echo.
echo ------------------------------
echo   Script finished. Press any key to close.
echo ------------------------------
pause >nul
``