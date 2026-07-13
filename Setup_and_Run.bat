@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ========================================
echo   %~nx0 - Setup ^& Launcher
echo   Project: %CD%
echo ========================================
echo.
echo   This window sets up and launches the program.
echo   Setup keeps everything inside this project folder where it can.
echo   You should not need to install anything system-wide unless a
echo   required tool (like Python) is completely missing from this PC.
echo.
echo   NOTE: The first time you run this, Windows (or your work
echo   security software) may show a warning because this file came
echo   from the internet. If you see "Windows protected your PC",
echo   click "More info" then "Run anyway" to continue. This is
echo   normal and only happens once.
echo.

:: ========================================
:: Configuration
:: ========================================
set "PYTHON_VERSION=3.11"
set "REQUIREMENTS=scripts\requirements.txt"
set "MAIN_SCRIPT=scripts\Universal\main.py"

:: Install scope for the rare case Python must be installed from scratch.
:: This is ONLY asked if Python is genuinely missing - see below.
set "INSTALL_SCOPE="

:: ========================================
:: Check for Python (the one unavoidable system dependency)
:: ========================================
:: A virtual environment cannot be created without a Python interpreter
:: already present, so this is the only tool we may have to install onto
:: the PC itself. If Python already exists, the user is never prompted.
echo Checking for Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo   Python is not installed on this PC, and it is required to run
    echo   this program. This is the only tool that has to be installed
    echo   onto the computer itself - everything else stays in this folder.
    echo.
    set "do_py="
    set /p do_py=Install Python now? ^(Y/N^):
    if /i "!do_py!"=="Y" (
        call :choose_scope
        call :install_python
    ) else (
        echo.
        echo   Python is required. You can install it manually from
        echo     https://www.python.org/downloads/
        echo   Make sure to check "Add python.exe to PATH" during installation.
        echo.
        pause
        exit /b 1
    )

    rem Re-check after attempted install
    python --version >nul 2>&1
    if !errorlevel! neq 0 (
        echo.
        echo   Python still not detected. You may need to close and
        echo   reopen this window so PATH changes take effect, then
        echo   run this file again.
        echo.
        pause
        exit /b 1
    )
)

:: Python 3.10 is the hard floor: the app uses syntax introduced in Python 3.10.
for /f "tokens=2,3 delims=. " %%a in ('python --version 2^>^&1') do (
    set "PY_MAJOR=%%a"
    set "PY_MINOR=%%b"
)
set "PY_TOO_OLD="
if !PY_MAJOR! lss 3 set "PY_TOO_OLD=1"
if !PY_MAJOR! equ 3 if !PY_MINOR! lss 10 set "PY_TOO_OLD=1"
if defined PY_TOO_OLD (
    echo   Python 3.10 or later is required to run this program.
    echo   Please install a newer Python version from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:: ========================================
:: Setup Virtual Environment (everything below stays in the repo)
:: ========================================
echo Setting up virtual environment...
if not exist ".venv\" (
    echo Creating new virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo   Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: Activate venv
call .venv\Scripts\activate.bat

:: ========================================
:: Install Dependencies (into the venv - never system-wide)
:: ========================================
if exist "%REQUIREMENTS%" (
    echo Installing dependencies into the project environment...
    python -m pip install --upgrade pip
    python -m pip install -r "%REQUIREMENTS%"
    if !errorlevel! neq 0 (
        echo.
        echo   ----------------------------------------------------------
        echo   SETUP COULD NOT FINISH: installing the required components
        echo   failed. The program has NOT been started.
        echo.
        echo   The most common cause is no internet connection. Please:
        echo     1. Check that you are connected to the internet.
        echo     2. Close this window and run this file again.
        echo   If it keeps failing, the message above this box shows the
        echo   exact error to share when asking for help.
        echo   ----------------------------------------------------------
        echo.
        pause
        exit /b 1
    )
) else (
    echo   Note: No requirements.txt found at %REQUIREMENTS%
    echo   Skipping dependency installation.
)

:: ========================================
:: Run the Application
:: ========================================
echo.
echo Launching application...
echo.

if exist "%MAIN_SCRIPT%" (
    python "%MAIN_SCRIPT%"
) else (
    echo   ERROR: Main script not found: %MAIN_SCRIPT%
    echo   Please create scripts\Universal\main.py or update this setup file.
    echo.
    pause
    exit /b 1
)

echo.
echo Program finished.
pause
endlocal
exit /b

:: ========================================
:: Helper: ask install scope (ONLY called when a system install is forced)
:: ========================================
:choose_scope
echo.
echo ----------------------------------------
echo   This install has to go onto the PC itself. Where should it go?
echo.
echo     1. Just for me        (no admin rights needed - safest at work)
echo     2. For all users      (requires admin rights on this PC)
echo ----------------------------------------
set "scope_choice="
set /p scope_choice=Enter 1 or 2 (default 1): 
if "%scope_choice%"=="2" (
    set "INSTALL_SCOPE=machine"
    echo   Installing system-wide (all users). Admin may be requested.
) else (
    set "INSTALL_SCOPE=user"
    echo   Installing for the current user only. No admin needed.
)
echo.
goto :eof

:: ========================================
:: Helper: install Python via winget at the chosen scope
:: ========================================
:install_python
echo   Installing Python (%INSTALL_SCOPE% scope)...
where winget >nul 2>&1
if %errorlevel% neq 0 (
    echo   Windows Package Manager ^(winget^) is not available.
    echo   Please install Python manually from:
    echo     https://www.python.org/downloads/
    echo   During install, check "Add python.exe to PATH".
    echo.
    pause
    goto :eof
)
if /i "%INSTALL_SCOPE%"=="machine" (
    winget install --id Python.Python.3.11 --scope machine --accept-source-agreements --accept-package-agreements
) else (
    winget install --id Python.Python.3.11 --scope user --accept-source-agreements --accept-package-agreements
)
goto :eof
