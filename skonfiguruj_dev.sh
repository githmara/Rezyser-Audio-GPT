#!/bin/bash
echo "=========================================="
echo "Konfiguracja srodowiska (Linux / macOS)"
echo "=========================================="

if ! command -v python3 &> /dev/null; then
    echo "BLAD KRYTYCZNY: Nie wykryto 'python3' w systemie!"
    exit 1
fi

echo "[1/2] Tworzenie wirtualnego srodowiska (venv)..."
python3 -m venv venv

echo "[2/2] Aktywacja srodowiska i instalacja zaleznosci..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "=========================================="
echo "Gotowe! Mozesz teraz uruchomic: ./Uruchom_Rezysera.sh"
echo "=========================================="