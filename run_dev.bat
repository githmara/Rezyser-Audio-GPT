@echo off
chcp 65001 >nul
set APP_DIR=%~dp0

:: 1. Release runtime (Windows only, shipped with ZIP/EXE)
if exist "%APP_DIR%runtime\python.exe" (
    set PYTHON_EXE="%APP_DIR%runtime\python.exe"
    goto :launch
)

:: 2. Dev venv (VS Code)
if exist "%APP_DIR%.venv\Scripts\python.exe" (
    set PYTHON_EXE="%APP_DIR%.venv\Scripts\python.exe"
    goto :launch
)

:: 3. Dev venv (classic)
if exist "%APP_DIR%venv\Scripts\python.exe" (
    set PYTHON_EXE="%APP_DIR%venv\Scripts\python.exe"
    goto :launch
)

:: 4. No environment found
echo =======================================================
echo  FATAL: No runtime environment found!
echo =======================================================
echo  Run `setup_dev.bat` first to create a venv and install dependencies.
echo =======================================================
pause
exit /b

:launch
"%PYTHON_EXE%" "%APP_DIR%main.py"
pause
