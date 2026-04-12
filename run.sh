#!/bin/bash
# BDO Trainer - macOS/Linux Run Script
# This script runs the BDO Trainer application

set -euo pipefail

# --- Change to the script's directory ---
cd "$(dirname "$0")"

echo "========================================"
echo "BDO Trainer - Starting Application"
echo "========================================"
echo

# --- Locate a usable Python 3 interpreter ---
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    # Make sure 'python' is actually Python 3
    if python --version 2>&1 | grep -q "Python 3"; then
        PYTHON="python"
    fi
fi

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3 is not installed or not in PATH"
    echo "Please install Python 3.8 or higher from https://www.python.org/"
    exit 1
fi

echo "Python found: $($PYTHON --version)"
echo

# --- Check for tkinter availability (before venv, using system Python) ---
PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if ! $PYTHON -c "import tkinter" &>/dev/null; then
    echo "ERROR: tkinter is not available for Python $PY_VERSION."
    echo "  macOS  – if you used Homebrew, run:  brew install python-tk@$PY_VERSION"
    echo "           (or install Python from python.org which bundles tkinter)"
    echo "  Linux  – install the package for your distro, e.g.:"
    echo "           sudo apt install python3-tk   (Debian/Ubuntu)"
    echo "           sudo dnf install python3-tkinter   (Fedora)"
    exit 1
fi

# --- Create virtual environment if it doesn't exist ---
VENV_DIR=""
if [ -d ".venv" ] && [ -f ".venv/bin/activate" ]; then
    VENV_DIR=".venv"
elif [ -d "venv" ] && [ -f "venv/bin/activate" ]; then
    VENV_DIR="venv"
fi

if [ -z "$VENV_DIR" ]; then
    # Clean up any Windows-created venv that won't work here
    for d in .venv venv; do
        if [ -d "$d" ] && [ ! -f "$d/bin/activate" ]; then
            echo "Found $d/ but it appears to be Windows-created (no bin/activate). Removing..."
            rm -rf "$d"
        fi
    done
    echo "Virtual environment not found. Creating one..."
    VENV_DIR=".venv"
    $PYTHON -m venv "$VENV_DIR"
    echo "Virtual environment created successfully!"
    echo
fi

# --- Activate virtual environment ---
echo "Activating virtual environment..."
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# --- Verify tkinter works inside the venv ---
if ! python -c "import tkinter" &>/dev/null; then
    echo "ERROR: tkinter is not available inside the virtual environment."
    echo "  This can happen if tkinter was installed after the venv was created."
    echo "  Try deleting the venv and re-running this script:"
    echo "    rm -rf $VENV_DIR && ./run.sh"
    exit 1
fi

# --- Install/update requirements if needed ---
if [ -f "requirements.txt" ]; then
    echo "Installing/updating dependencies from requirements.txt..."
    pip install -r requirements.txt --quiet
fi

echo
echo "========================================"
echo "Starting BDO Trainer..."
echo "========================================"
echo

# --- Platform-specific notes ---
if [ "$(uname)" = "Darwin" ]; then
    echo "NOTE (macOS): If this is your first run, the app will prompt for"
    echo "Accessibility permissions via a system dialog."
    echo
fi

# NOTE: The 'keyboard' Python library typically requires root/sudo on Linux
# to capture global key events. If hotkeys don't work, try running with:
#   sudo ./run.sh
# We intentionally do NOT auto-elevate; just inform the user.
if [ "$(uname)" = "Linux" ]; then
    echo "NOTE (Linux): The keyboard library may require root privileges for"
    echo "global hotkey capture. If hotkeys don't work, try:  sudo ./run.sh"
    echo
fi

# --- Run the application ---
python main.py "$@"
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo
    echo "========================================"
    echo "Application exited with an error (code $EXIT_CODE)"
    echo "========================================"
    exit $EXIT_CODE
fi

echo
echo "========================================"
echo "Application closed successfully"
echo "========================================"
