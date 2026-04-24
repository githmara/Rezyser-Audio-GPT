#!/bin/bash
echo "=========================================="
echo " Dev environment setup (Linux / macOS)"
echo "=========================================="

if ! command -v python3 &> /dev/null; then
    echo "FATAL: 'python3' not found in PATH!"
    exit 1
fi

echo "[1/2] Creating virtual environment (venv)..."
python3 -m venv venv

echo "[2/2] Activating the venv and installing dependencies from requirements.txt..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "=========================================="
echo " Done! Launch the app with: ./run.sh"
echo "=========================================="
