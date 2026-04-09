@echo off
chcp 65001 >nul
set APP_DIR=%~dp0

:: 1. Srodowisko Wydawnicze (Tylko Windows)
if exist "%APP_DIR%runtime\python.exe" (
    set PYTHON_EXE="%APP_DIR%runtime\python.exe"
    goto :uruchom
)

:: 2. Srodowisko Deweloperskie (VS Code)
if exist "%APP_DIR%.venv\Scripts\python.exe" (
    set PYTHON_EXE="%APP_DIR%.venv\Scripts\python.exe"
    goto :uruchom
)

:: 3. Srodowisko Deweloperskie (Klasyczne)
if exist "%APP_DIR%venv\Scripts\python.exe" (
    set PYTHON_EXE="%APP_DIR%venv\Scripts\python.exe"
    goto :uruchom
)

:: 4. Brak srodowiska
echo =======================================================
echo BLAD KRYTYCZNY: Nie znaleziono srodowiska uruchomieniowego!
echo =======================================================
echo Uruchom najpierw plik "skonfiguruj_dev.bat", aby zainstalowac biblioteki.
echo =======================================================
pause
exit /b

:uruchom
%PYTHON_EXE% -m streamlit run "%APP_DIR%Start.py"
pause