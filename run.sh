#!/bin/bash
# BDO Trainer — macOS / Linux run script.
#
# Picks a known-good Python version, creates / refreshes the venv,
# installs requirements, and launches main.py.
#
# Python 3.14 + current pyobjc has a lazy-import bug that crashes
# the macOS keyboard listener thread (KeyError: 'AXIsProcessTrusted').
# We prefer 3.13 → 3.12 → 3.11 on macOS specifically; if the only
# Python on PATH is 3.14, we run anyway with a warning so the user
# can still launch in non-input-monitored mode.

set -euo pipefail

cd "$(dirname "$0")"

echo "========================================"
echo "BDO Trainer — Starting Application"
echo "========================================"
echo

# --- Python detection ------------------------------------------------------
# Preference order. On macOS we explicitly bias away from 3.14
# because of the pyobjc lazy-import bug; on Linux the order is
# the same but the bias doesn't matter.
PREFERRED_PY=("python3.13" "python3.12" "python3.11" "python3" "python")

PYTHON=""
for cand in "${PREFERRED_PY[@]}"; do
    if command -v "$cand" &>/dev/null; then
        # Only accept Python 3 — 'python' on some systems is still 2.x.
        if "$cand" --version 2>&1 | grep -q "Python 3"; then
            PYTHON="$cand"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: No Python 3 interpreter found on PATH."
    echo
    echo "Install one of these (in preference order):"
    echo "  • Python 3.13 (recommended)"
    echo "  • Python 3.12"
    echo "  • Python 3.11"
    echo
    echo "macOS:    brew install python@3.13"
    echo "          (or download from https://www.python.org/)"
    echo "Linux:    sudo apt install python3.13 python3.13-venv python3.13-tk"
    echo "          (Debian/Ubuntu — substitute your distro's package manager)"
    exit 1
fi

PY_FULL_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
PY_MAJOR_MINOR=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python found: $PYTHON ($PY_FULL_VERSION)"

# Warn loudly if the user is on macOS + 3.14. The trainer has a
# fallback for the pyobjc bug (logs a warning, runs without input
# monitoring), but the user almost always wants input monitoring.
if [ "$(uname)" = "Darwin" ] && [ "$PY_MAJOR_MINOR" = "3.14" ]; then
    echo
    echo "⚠  WARNING: Python 3.14 has a known pyobjc bug on macOS that"
    echo "   breaks pynput's keyboard listener. The trainer will run"
    echo "   but key presses won't drive combo advancement."
    echo
    echo "   To fix: install Python 3.13 (brew install python@3.13)"
    echo "   then delete .venv/ and re-run this script. We'll pick"
    echo "   up the 3.13 interpreter automatically."
    echo
fi

# --- tkinter check (system Python) -----------------------------------------
if ! "$PYTHON" -c "import tkinter" &>/dev/null; then
    echo "ERROR: tkinter is not available for $PYTHON ($PY_FULL_VERSION)."
    echo "  macOS:  brew install python-tk@$PY_MAJOR_MINOR"
    echo "          (or install Python from python.org which bundles tkinter)"
    echo "  Linux:  sudo apt install python3-tk      (Debian/Ubuntu)"
    echo "          sudo dnf install python3-tkinter (Fedora)"
    exit 1
fi

# --- venv selection / recreation -------------------------------------------
VENV_DIR=""
for d in .venv venv; do
    if [ -d "$d" ] && [ -f "$d/bin/activate" ]; then
        VENV_DIR="$d"
        break
    fi
done

# Delete any stale Windows-layout venv. They'll have Scripts/ but
# no bin/, which won't run from a POSIX shell.
for d in .venv venv; do
    if [ -d "$d" ] && [ ! -f "$d/bin/activate" ]; then
        echo "Removing stale Windows-layout venv at $d/ …"
        rm -rf "$d"
        if [ "$VENV_DIR" = "$d" ]; then VENV_DIR=""; fi
    fi
done

# If the existing venv's Python differs from the one we'd pick now,
# recreate. Common case — user upgrades Python or installs a newer
# minor version and the old venv is pinned to the old one.
if [ -n "$VENV_DIR" ]; then
    VENV_PY="$VENV_DIR/bin/python"
    if [ -x "$VENV_PY" ]; then
        VENV_VERSION=$("$VENV_PY" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "?")
        if [ "$VENV_VERSION" != "$PY_MAJOR_MINOR" ]; then
            echo "Existing venv uses Python $VENV_VERSION but $PY_MAJOR_MINOR is preferred."
            echo "Recreating $VENV_DIR/ with $PYTHON …"
            rm -rf "$VENV_DIR"
            VENV_DIR=""
        fi
    fi
fi

if [ -z "$VENV_DIR" ]; then
    echo "Creating virtual environment with $PYTHON …"
    VENV_DIR=".venv"
    "$PYTHON" -m venv "$VENV_DIR"
    echo "Virtual environment created at $VENV_DIR/."
    echo
fi

# --- Activate --------------------------------------------------------------
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# tkinter must work *inside* the venv too — sometimes a host's
# tkinter is broken even though the system Python loads it fine.
if ! python -c "import tkinter" &>/dev/null; then
    echo "ERROR: tkinter not available inside the venv."
    echo "  Try: rm -rf $VENV_DIR && ./run.sh"
    exit 1
fi

# --- Install / update requirements -----------------------------------------
if [ -f "requirements.txt" ]; then
    echo "Installing / updating dependencies …"
    pip install -r requirements.txt --quiet
fi

# --- macOS pyobjc smoke test ----------------------------------------------
# Surfaces the input-monitor disable up front so the user knows
# whether key presses will drive the trainer.
if [ "$(uname)" = "Darwin" ]; then
    if ! python -c "import HIServices; HIServices.AXIsProcessTrusted" &>/dev/null; then
        echo
        echo "⚠  Input monitoring will be DISABLED on this venv —"
        echo "   pyobjc's HIServices.AXIsProcessTrusted can't be"
        echo "   resolved (known bug on Python 3.14). The trainer"
        echo "   will run; tray + overlay + chain renderer all work,"
        echo "   but key presses won't auto-advance combos."
        echo
        echo "   Fix: install Python 3.13, delete $VENV_DIR/, re-run."
        echo
    fi
fi

# --- Platform notes --------------------------------------------------------
echo "========================================"
echo "Starting BDO Trainer …"
echo "========================================"
echo

if [ "$(uname)" = "Darwin" ]; then
    echo "NOTE (macOS): On first run the app will prompt for"
    echo "Accessibility permissions via a system dialog. Grant them"
    echo "for input monitoring to work."
    echo
fi

if [ "$(uname)" = "Linux" ]; then
    echo "NOTE (Linux): The 'keyboard' library may require root for"
    echo "global hotkey capture. If hotkeys don't work, try:"
    echo "  sudo ./run.sh"
    echo
fi

# --- Launch ----------------------------------------------------------------
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
