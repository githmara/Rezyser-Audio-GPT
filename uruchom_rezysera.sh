#!/bin/bash
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Szukamy folderów venv (utworzonych ręcznie lub przez VS Code)
if [ -f "$APP_DIR/.venv/bin/python" ]; then
    PYTHON_EXE="$APP_DIR/.venv/bin/python"
elif [ -f "$APP_DIR/venv/bin/python" ]; then
    PYTHON_EXE="$APP_DIR/venv/bin/python"
else
    echo "======================================================="
    echo "BLAD: Nie znaleziono srodowiska (venv ani .venv)."
    echo "Uruchom najpierw skrypt: ./skonfiguruj_dev.sh"
    echo "======================================================="
    exit 1
fi

"$PYTHON_EXE" -m streamlit run "$APP_DIR/Start.py"