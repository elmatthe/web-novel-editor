#!/bin/bash

# ========================================
# Setup & Launcher for macOS
# ========================================

cd "$(dirname "$0")"

echo "========================================"
echo "$(basename "$0") - Setup & Launcher"
echo "Project: $(pwd)"
echo "========================================"
echo
echo "  This window sets up and launches the program."
echo "  Setup keeps everything inside this project folder where it can."
echo "  You should not need to install anything system-wide unless a"
echo "  required tool (like Python) is completely missing from this Mac."
echo
echo "  NOTE: The first time you open this, macOS (or your work"
echo "  security software) may block it because it came from the"
echo "  internet. If you see \"cannot be opened\", go to"
echo "  System Settings > Privacy & Security, scroll down, and click"
echo "  \"Open Anyway\". This is normal and only happens once."
echo

# ========================================
# Configuration
# ========================================
PYTHON_VERSION="3.11"
REQUIREMENTS="scripts/requirements.txt"
MAIN_SCRIPT="scripts/main.py"

# Install scope for the rare case Python must be installed from scratch.
# Only asked if Python is genuinely missing - see below.
INSTALL_SCOPE=""

# ========================================
# Helper: ask install scope (ONLY when a system install is forced)
# ========================================
choose_scope() {
    echo
    echo "----------------------------------------"
    echo "  This install has to go onto the Mac itself. Where should it go?"
    echo
    echo "    1. Just for me        (no admin password needed - safest at work)"
    echo "    2. For all users      (may require an admin password)"
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

# ========================================
# Helper: ensure Homebrew (user-local, no sudo) when needed
# ========================================
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
    else
        return 1
    fi
}

# ========================================
# Check for Python (the one unavoidable system dependency)
# ========================================
# A virtual environment cannot be created without a Python interpreter
# already present, so this is the only tool we may have to install onto
# the Mac itself. If Python already exists, the user is never prompted.
echo "Checking for Python..."
if ! command -v python3 &> /dev/null; then
    echo
    echo "  Python 3 is not installed on this Mac, and it is required to"
    echo "  run this program. This is the only tool that has to be installed"
    echo "  onto the computer itself - everything else stays in this folder."
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
                brew install "python@${PYTHON_VERSION}"
            else
                echo "  Skipped. Python is required to run this program."
                read -p "Press Enter to exit..."
                exit 1
            fi
        fi
    else
        echo "  Python is required. Install it from https://www.python.org/downloads/macos/"
        read -p "Press Enter to exit..."
        exit 1
    fi

    # Re-check
    if ! command -v python3 &> /dev/null; then
        echo
        echo "  Python still not detected. Try closing and reopening this"
        echo "  window so PATH changes take effect, then run it again."
        read -p "Press Enter to exit..."
        exit 1
    fi
fi

# Python 3.10 is the hard floor: the app uses syntax introduced in Python 3.10.
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"; then
    echo
    echo "  Python 3.10 or later is required to run this program."
    echo "  Please install a newer Python version, then run this file again."
    read -p "Press Enter to exit..."
    exit 1
fi

# ========================================
# Setup Virtual Environment (everything below stays in the repo)
# ========================================
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo "Failed to create virtual environment."
        read -p "Press Enter to exit..."
        exit 1
    fi
fi

# Activate venv
source .venv/bin/activate

# ========================================
# Install Dependencies (into the venv - never system-wide)
# ========================================
if [ -f "$REQUIREMENTS" ]; then
    echo "Installing dependencies into the project environment..."
    pip install --upgrade pip
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
else
    echo "Note: No requirements.txt found at $REQUIREMENTS"
fi

# ========================================
# Run the Application
# ========================================
echo
echo "Launching application..."
echo

if [ -f "$MAIN_SCRIPT" ]; then
    python "$MAIN_SCRIPT"
else
    echo "ERROR: Main script not found: $MAIN_SCRIPT"
    echo "Please create scripts/main.py or update this file."
    echo
fi

echo
echo "Program finished."
read -p "Press Enter to close..."
