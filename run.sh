#!/bin/bash
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Look for a venv folder created manually or by VS Code.
if [ -f "$APP_DIR/.venv/bin/python" ]; then
    PYTHON_EXE="$APP_DIR/.venv/bin/python"
elif [ -f "$APP_DIR/venv/bin/python" ]; then
    PYTHON_EXE="$APP_DIR/venv/bin/python"
else
    echo "======================================================="
    echo " FATAL: No environment found (.venv or venv)."
    echo " Run ./setup_dev.sh first to create a venv."
    echo "======================================================="
    exit 1
fi

"$PYTHON_EXE" "$APP_DIR/main.py"
