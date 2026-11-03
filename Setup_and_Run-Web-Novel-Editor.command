#!/bin/bash
# ============================================================================
#  Web Novel Editor  --  macOS setup + launcher (double-click from Finder)
# ============================================================================
#  [Step 1 of 3] A healthy project environment (.venv) is checked offline and the
#                program starts immediately. No internet, no installs.
#  [Step 2 of 3] Otherwise a separate Python 3.10+ is located (python.org or
#                Homebrew installs; never Apple's /usr/bin/python3 stub). If none
#                exists you are guided to the official python.org installer.
#  [Step 3 of 3] scripts/bootstrap.py repairs or rebuilds .venv, installs the
#                exact pinned packages (this may need internet), proves the
#                environment healthy and starts the program.
#  Re-running this file is always the repair path. Logs: files/runtime-data/logs.
#  This file must keep the .command extension, LF line endings and chmod +x.
# ============================================================================

cd "$(dirname "$0")" || exit 1
export PYTHONIOENCODING=utf-8

VENV_PY=".venv/bin/python"
BOOTSTRAP="scripts/bootstrap.py"
LOG_DIR="files/runtime-data/logs"
PYTHON_URL="https://www.python.org/downloads/macos/"
BASE_PY=""
RC=0

hold() {
    echo
    read -r -p "Press Enter to close this window..." _
    exit "$1"
}

# try_python PATH: accept an existing, non-Apple-stub interpreter that runs and is 3.10+.
try_python() {
    [ -n "$BASE_PY" ] && return 0
    [ -x "$1" ] || return 1
    [ "$1" = "/usr/bin/python3" ] && return 1
    if "$1" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >/dev/null 2>&1; then
        BASE_PY="$1"
        return 0
    fi
    return 1
}

find_python() {
    BASE_PY=""
    local candidate
    for candidate in $(ls -d /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 2>/dev/null | sort -r); do
        try_python "$candidate"
    done
    for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3; do
        try_python "$candidate"
    done
    candidate="$(command -v python3 2>/dev/null)"
    [ -n "$candidate" ] && try_python "$candidate"
    return 0
}

offer_python_install() {
    echo
    echo "  Python 3.10 or newer is needed to run Web Novel Editor and was not found."
    echo "  Install it with the official installer from:"
    echo "    ${PYTHON_URL}"
    read -r -p "  Open that page now? (Y/N): " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        open "$PYTHON_URL" >/dev/null 2>&1
        read -r -p "  Press Enter after Python has finished installing..." _
    fi
}

echo "============================================================"
echo "  Web Novel Editor - Setup and Launcher"
echo "  Folder: $(pwd)"
echo "============================================================"
echo
echo "  First-run note: if macOS says the file cannot be opened, use"
echo "  System Settings > Privacy & Security > Open Anyway. This only happens once."
echo

if [ ! -f "$BOOTSTRAP" ]; then
    echo "ERROR: The setup helper is missing: $BOOTSTRAP"
    echo "Please download a fresh copy of the program."
    hold 10
fi

if [ -x "$VENV_PY" ]; then
    echo "[Step 1 of 3] Checking the existing program environment (offline)..."
    "$VENV_PY" "$BOOTSTRAP" --launch-only
    RC=$?
    if [ "$RC" -eq 0 ]; then
        echo
        echo "  Web Novel Editor is running in its own window. You can close this window."
        hold 0
    fi
    if [ "$RC" -eq 4 ]; then
        echo
        echo "ERROR: Web Novel Editor could not start. The details are shown above."
        echo "Logs are in: $LOG_DIR"
        hold 4
    fi
    echo "  Setup or repair is needed."
fi

echo
echo "[Step 2 of 3] Looking for Python 3.10 or newer..."
find_python
if [ -z "$BASE_PY" ] && [ ! -x "$VENV_PY" ]; then
    offer_python_install
    find_python
fi

echo
if [ -n "$BASE_PY" ]; then
    echo "  Using Python: $BASE_PY"
    echo "[Step 3 of 3] Setting up and starting (the first time can take a few minutes)..."
    "$BASE_PY" "$BOOTSTRAP"
    RC=$?
elif [ -x "$VENV_PY" ]; then
    echo "  No separate Python was found; repairing in place with the existing environment."
    echo "[Step 3 of 3] Repairing and starting..."
    "$VENV_PY" "$BOOTSTRAP"
    RC=$?
else
    echo "  Python 3.10 or newer is required and was not found."
    echo "  Install it from ${PYTHON_URL}, then run this file again."
    hold 10
fi

case "$RC" in
    0) echo; echo "  Web Novel Editor is running in its own window. You can close this window." ;;
    2) echo; echo "Setup was cancelled. Nothing else was changed." ;;
    4) echo; echo "ERROR: Web Novel Editor could not start. The details are shown above."
       echo "Logs are in: $LOG_DIR" ;;
    *) echo; echo "ERROR: Setup did not complete (code $RC). The message above explains why."
       echo "Logs are in: $LOG_DIR" ;;
esac
hold "$RC"
