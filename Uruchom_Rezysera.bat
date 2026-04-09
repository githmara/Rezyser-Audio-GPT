@echo off
chcp 65001 >nul
set APP_DIR=%~dp0

:: 1. Szukamy wersji Portable (lokalny Python w folderze runtime)
if exist "%APP_DIR%runtime\python.exe" (
    set PYTHON_EXE="%APP_DIR%runtime\python.exe"
    echo [System] Wykryto folder runtime. Uruchamianie w trybie Portable...
    goto :uruchom
)

:: 2. Szukamy wersji Deweloperskiej (wirtualne srodowisko venv)
if exist "%APP_DIR%venv\Scripts\python.exe" (
    set PYTHON_EXE="%APP_DIR%venv\Scripts\python.exe"
    echo [System] Wykryto folder venv. Uruchamianie w trybie Deweloperskim...
    goto :uruchom
)

:: 3. Brak srodowiska - komunikat bledu
echo =======================================================
echo BLAD KRYTYCZNY: Nie znaleziono srodowiska uruchomieniowego!
echo =======================================================
echo Jesli jestes uzytkownikiem koncowym: 
echo Prawdopodobnie uszkodziles folder "runtime". Pobierz aplikacje ponownie ze strony wydania.
echo.
echo Jesli jestes programista (sklonowales repozytorium):
echo Uruchom najpierw plik "skonfiguruj_dev.bat", aby utworzyc srodowisko "venv" i pobrac zaleznosci.
echo =======================================================
pause
exit /b

:uruchom
%PYTHON_EXE% -m streamlit run "%APP_DIR%Start.py"
pause