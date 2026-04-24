@echo off
chcp 65001 >nul
echo ==========================================
echo  Dev environment setup (Windows)
echo ==========================================

echo [1/3] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo FATAL: Python not found in PATH!
    echo Install Python from the official site and make sure it is added to PATH.
    pause
    exit /b
)

echo [2/3] Creating virtual environment (venv)...
python -m venv venv

echo [3/3] Activating the venv and installing dependencies from requirements.txt...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

echo ==========================================
echo  Done! Dev environment ready.
echo ==========================================
echo  Launch the app with `run_dev.bat` (runs main.py inside the venv).
echo ==========================================
pause
