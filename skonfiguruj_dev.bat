@echo off
chcp 65001 >nul
echo ==========================================
echo Konfiguracja srodowiska deweloperskiego
echo ==========================================

echo [1/3] Sprawdzanie instalacji Pythona...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo BLAD KRYTYCZNY: Nie wykryto Pythona w systemie! 
    echo Zainstaluj Pythona z oficjalnej strony i upewnij sie, ze dodales go do zmiennej PATH.
    pause
    exit /b
)

echo [2/3] Tworzenie wirtualnego srodowiska (venv)...
python -m venv venv

echo [3/3] Aktywacja srodowiska i instalacja zaleznosci...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

echo ==========================================
echo Gotowe! Srodowisko deweloperskie zostalo pomyslnie przygotowane.
echo ==========================================
echo Mozesz teraz uruchomic plik `uruchom_rezysera.bat, co powinno uruchomic aplikacje w trybie deweloperskim.
echo ==========================================
pause