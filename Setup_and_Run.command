#!/bin/bash
# ============================================================================
#  Web Novel Editor  --  macOS setup + launcher
# ============================================================================
#  One double-click does everything for a NON-TECHNICAL user:
#    [Step 1 of 4] Check Python and the existing project environment.
#    [Step 2 of 4] Create/repair the virtual environment (self-healing).
#    [Step 3 of 4] Install dependencies into the venv, with a health check.
#    [Step 4 of 4] Preflight, then launch the GUI.
#
#  SELF-HEALING: delete .venv (or an incomplete one is detected automatically)
#  and re-run -- it rebuilds from scratch. Delete Python and re-run -- it
#  detects the absence and offers to reinstall. Re-running always returns you
#  to a working state.
#
#  This file MUST keep the .command extension (so it opens on double-click from
#  Finder) and MUST be executable (chmod +x). Its line endings are LF.
#
#  Goal: the MINIMUM installed on the Mac (only Python, and only if missing);
#  everything else contained in the repo and the venv.
# ============================================================================

cd "$(dirname "$0")" || exit 1

# ============================================================================
#  Configuration
# ============================================================================
PROJECT_NAME="Web Novel Editor"

# Minimum Python major.minor. This is a HARD FLOOR: the app uses syntax
# introduced in Python 3.10, so the launcher STOPS (does not just warn) below it.
PY_MIN_MAJOR="3"
PY_MIN_MINOR="10"
# Homebrew formula used if Python must be installed from scratch (user scope).
PYTHON_BREW_FORMULA="python@3.11"

REQUIREMENTS="scripts/requirements.txt"
MAIN_SCRIPT="scripts/Universal/main.py"

VENV_DIR=".venv"
VENV_ACTIVATE=".venv/bin/activate"
VENV_PY=".venv/bin/python"
LOCK=".venv/requirements.lock"

# Internal state.
INSTALL_SCOPE=""
PYTHON_CMD=""

# ============================================================================
#  Banner + first-run security note
# ============================================================================
clear 2>/dev/null
echo "========================================"
echo "  ${PROJECT_NAME} - Setup & Launcher"
echo "  Folder: $(pwd)"
echo "========================================"
echo
echo "  This window sets up and launches the program. Setup keeps everything"
echo "  inside this project folder where it can. You should not need to install"
echo "  anything system-wide unless a required tool (Python) is completely"
echo "  missing from this Mac -- and it will ask you first if so."
echo
echo "  FIRST-RUN NOTE: Because this file came from the internet, macOS may"
echo "  block it the first time. If you see \"cannot be opened\", go to"
echo "  System Settings > Privacy & Security, scroll down, and click"
echo "  \"Open Anyway\". This is normal and only happens once."
echo

# ============================================================================
#  Helpers
# ============================================================================

# Find a usable system Python 3 and store it in PYTHON_CMD. Returns 0 if found.
detect_python() {
    PYTHON_CMD=""
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
        return 0
    fi
    return 1
}

# VENV_COMPLETE=1 if .venv exists, has an interpreter, and that interpreter meets
# the minimum version. (Dependency freshness is checked separately.)
VENV_COMPLETE=""
check_venv_complete() {
    VENV_COMPLETE=""
    [ -f "$VENV_ACTIVATE" ] || return 0
    [ -x "$VENV_PY" ] || return 0
    if "$VENV_PY" -c "import sys; sys.exit(0 if sys.version_info >= (${PY_MIN_MAJOR}, ${PY_MIN_MINOR}) else 1)" >/dev/null 2>&1; then
        VENV_COMPLETE="1"
    fi
}

# DEPS_OK=1 only if the venv is provably healthy: the lock matches
# requirements.txt, "pip check" is clean, and the required packages import.
# (Run after the venv is activated so "python" is the venv interpreter.)
DEPS_OK=""
check_deps_ok() {
    DEPS_OK=""
    [ -f "$LOCK" ] || return 0
    [ -f "$REQUIREMENTS" ] || return 0
    cmp -s "$LOCK" "$REQUIREMENTS" || return 0
    python -m pip check >/dev/null 2>&1 || return 0
    python -c "import pdfplumber, reportlab" >/dev/null 2>&1 || return 0
    DEPS_OK="1"
}

# Ask user vs machine scope. ONLY called when a forced system install happens.
choose_scope() {
    echo
    echo "----------------------------------------"
    echo "  This install has to go onto the Mac itself. Where should it go?"
    echo
    echo "    1. Just for me     (no admin password needed - safest at work)"
    echo "    2. For all users   (may require an admin password)"
    echo "----------------------------------------"
    read -p "Enter 1 or 2 (default 1): " scope_choice
    if [ "$scope_choice" = "2" ]; then
        INSTALL_SCOPE="machine"
        echo "  Installing system-wide. You may be asked for an admin password."
    else
        INSTALL_SCOPE="user"
        echo "  Installing for the current user only. No admin password needed."
    fi
    echo
}

# Ensure Homebrew (user-local, no sudo) is available. Returns 0 on success.
ensure_homebrew() {
    if command -v brew &> /dev/null; then
        return 0
    fi
    echo
    echo "  Homebrew (the macOS installer tool) is not installed."
    read -p "  Install Homebrew now? (Y/N): " do_brew
    if [[ "$do_brew" =~ ^[Yy]$ ]]; then
        echo "  Installing Homebrew into your user account..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        if [ -x /opt/homebrew/bin/brew ]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [ -x /usr/local/bin/brew ]; then
            eval "$(/usr/local/bin/brew shellenv)"
        fi
        command -v brew &> /dev/null && return 0
    fi
    return 1
}

# ============================================================================
#  [Step 1 of 4] - Python and existing-environment check
# ============================================================================
# Prefer an already-healthy venv on a normal repeat launch: if .venv is complete
# and on a compatible Python, no system Python is needed at all.
echo "[Step 1 of 4] Checking Python and the project environment..."
check_venv_complete
if [ -n "$VENV_COMPLETE" ]; then
    echo "  Existing project environment looks good - reusing it."
else
    # The venv must be (re)built, so a compatible system Python is required.
    if ! detect_python; then
        echo
        echo "  Python 3 is not installed on this Mac, and it is required to run this"
        echo "  program. This is the ONLY tool that has to be installed onto the"
        echo "  computer itself - everything else stays in this folder."
        echo
        read -p "  Install Python now? (Y/N): " do_py
        if [[ "$do_py" =~ ^[Yy]$ ]]; then
            choose_scope
            if [ "$INSTALL_SCOPE" = "machine" ]; then
                echo "  Please install Python system-wide from python.org:"
                echo "    https://www.python.org/downloads/macos/"
                echo "  (The official installer may require an admin password.)"
                read -p "  Press Enter once Python is installed to continue..."
            else
                if ensure_homebrew; then
                    echo "  Installing Python via Homebrew (no admin password)..."
                    brew install "$PYTHON_BREW_FORMULA"
                else
                    echo "  Skipped. Python is required to run this program."
                    read -p "Press Enter to exit..."
                    exit 1
                fi
            fi
        else
            echo "  Python is required. Install it from:"
            echo "    https://www.python.org/downloads/macos/"
            echo "  then run this file again."
            read -p "Press Enter to exit..."
            exit 1
        fi

        # Re-detect; a fresh install may not be on PATH in this same window.
        if ! detect_python; then
            echo
            echo "  Python was installed but isn't visible in THIS window yet. Close"
            echo "  this window, re-open it, and run this file again so the updated"
            echo "  PATH takes effect."
            read -p "Press Enter to exit..."
            exit 1
        fi
    fi

    # HARD version gate on the interpreter that will build the venv: STOP, not warn.
    if ! "$PYTHON_CMD" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"; then
        echo
        echo "  Python 3.10 or later is required to run this program."
        echo "  Please install a newer Python version, then run this file again."
        read -p "Press Enter to exit..."
        exit 1
    fi
    echo "  Using Python command: $PYTHON_CMD"
fi

# ============================================================================
#  [Step 2 of 4] - Virtual environment (self-healing)
# ============================================================================
echo "[Step 2 of 4] Setting up the virtual environment..."
if [ -n "$VENV_COMPLETE" ]; then
    echo "  Reusing the existing virtual environment."
else
    if [ -d "$VENV_DIR" ]; then
        echo "  The existing environment is incomplete or outdated - rebuilding it..."
        rm -rf "$VENV_DIR"
    else
        echo "  Creating a fresh virtual environment in this folder..."
    fi
    if ! "$PYTHON_CMD" -m venv "$VENV_DIR"; then
        echo "  ERROR: Failed to create the virtual environment."
        read -p "Press Enter to exit..."
        exit 1
    fi
fi

# Activate the venv so "python" below is the project's own interpreter.
# shellcheck disable=SC1091
source "$VENV_ACTIVATE"
if [ ! -f "$VENV_ACTIVATE" ]; then
    echo "  ERROR: Virtual environment activation script missing after setup."
    read -p "Press Enter to exit..."
    exit 1
fi

# ============================================================================
#  [Step 3 of 4] - Dependencies (idempotent, health-gated)
# ============================================================================
# Only skip the install when the environment is provably healthy: a matching
# requirements lock, "pip check" clean, and the required packages importable.
echo "[Step 3 of 4] Checking dependencies..."
check_deps_ok
if [ -n "$DEPS_OK" ]; then
    echo "  Dependencies are already installed and healthy - skipping install."
elif [ ! -f "$REQUIREMENTS" ]; then
    echo "  Note: No requirements.txt at $REQUIREMENTS - skipping dependencies."
else
    echo "  Installing dependencies into the project environment..."
    pip install --upgrade pip >/dev/null 2>&1
    pip install -r "$REQUIREMENTS"
    if [ $? -ne 0 ]; then
        echo
        echo "  ----------------------------------------------------------"
        echo "  SETUP COULD NOT FINISH: installing the required components"
        echo "  failed. The program has NOT been started."
        echo
        echo "  The most common cause is no internet connection. Please:"
        echo "    1. Check that you are connected to the internet."
        echo "    2. Close this window and run this file again."
        echo "  If it keeps failing, the message above this box shows the"
        echo "  exact error to share when asking for help."
        echo "  ----------------------------------------------------------"
        echo
        read -p "Press Enter to exit..."
        exit 1
    fi
    # Validate the freshly-installed environment BEFORE trusting it.
    if ! python -m pip check >/dev/null 2>&1; then
        echo "  ERROR: The environment failed its health check (pip check) after install."
        echo "  Close this window and run this file again."
        read -p "Press Enter to exit..."
        exit 1
    fi
    if ! python -c "import pdfplumber, reportlab" >/dev/null 2>&1; then
        echo "  ERROR: A required component could not be imported after install."
        echo "  Close this window and run this file again."
        read -p "Press Enter to exit..."
        exit 1
    fi
    # Write the lock ONLY after a successful install AND a passing health check.
    cp -f "$REQUIREMENTS" "$LOCK" 2>/dev/null
fi

# ============================================================================
#  [Step 4 of 4] - Preflight, then launch the GUI
# ============================================================================
echo "[Step 4 of 4] Starting ${PROJECT_NAME}..."
if [ ! -f "$MAIN_SCRIPT" ]; then
    echo "  ERROR: Main script not found: $MAIN_SCRIPT"
    echo "  Please reinstall the program from a fresh copy of the release."
    read -p "Press Enter to exit..."
    exit 1
fi

# Preflight so a fatal startup error is visible before the GUI takes over.
echo "  Checking the program can start..."
python "$MAIN_SCRIPT" --check
if [ $? -ne 0 ]; then
    echo
    echo "  The program could not start. The details are shown above."
    echo "  Close this window and run this file again, or ask for help with"
    echo "  the message shown above."
    echo
    read -p "Press Enter to exit..."
    exit 1
fi

echo "  Launching ${PROJECT_NAME}..."
python "$MAIN_SCRIPT"
RUN_EXIT=$?

echo
if [ "$RUN_EXIT" -ne 0 ]; then
    echo "Program exited with code ${RUN_EXIT}."
else
    echo "Program finished."
fi
read -p "Press Enter to close..."
exit $RUN_EXIT
