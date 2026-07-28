@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

:: ============================================================================
::  Web Novel Editor  --  Windows setup + launcher
:: ============================================================================
::  One double-click does everything for a NON-TECHNICAL user:
::    [Step 1 of 4] Check Python and the existing project environment.
::    [Step 2 of 4] Create/repair the virtual environment (self-healing).
::    [Step 3 of 4] Install dependencies into the venv, with a health check.
::    [Step 4 of 4] Preflight, then launch the GUI (no console window).
::
::  SELF-HEALING: delete .venv (or an incomplete one is detected automatically)
::  and re-run -- it rebuilds from scratch. Delete Python and re-run -- it
::  detects the absence and offers to reinstall. Re-running always returns you
::  to a working state.
::
::  Goal: the MINIMUM installed on the PC (only Python, and only if missing);
::  everything else contained in the repo and the venv.
:: ============================================================================

:: ============================================================================
::  Configuration
:: ============================================================================
set "PROJECT_NAME=Web Novel Editor"

:: Minimum Python major.minor. This is a HARD FLOOR: the app uses syntax
:: introduced in Python 3.10, so the launcher STOPS (does not just warn) below it.
set "PY_MIN_MAJOR=3"
set "PY_MIN_MINOR=10"
:: Version winget installs if Python must be installed from scratch.
set "PYTHON_WINGET_ID=Python.Python.3.11"

set "REQUIREMENTS=scripts\requirements.txt"
set "MAIN_SCRIPT=scripts\Universal\main.py"

set "VENV_DIR=.venv"
set "VENV_ACTIVATE=.venv\Scripts\activate.bat"
set "VENV_PY=.venv\Scripts\python.exe"
set "VENV_PYW=.venv\Scripts\pythonw.exe"
set "LOCK=.venv\requirements.lock"

:: Internal state.
set "INSTALL_SCOPE="
set "FATAL="

:: ============================================================================
::  Banner + first-run security note
:: ============================================================================
cls
echo ========================================
echo   %PROJECT_NAME% - Setup ^& Launcher
echo   Folder: %CD%
echo ========================================
echo.
echo   This window sets up and launches the program. Setup keeps everything
echo   inside this project folder where it can. You should not need to install
echo   anything system-wide unless a required tool (Python) is completely
echo   missing from this PC -- and it will ask you first if so.
echo.
echo   FIRST-RUN NOTE: Because this file came from the internet, Windows (or
echo   your work security software) may warn you the first time. If you see
echo   "Windows protected your PC", click "More info" then "Run anyway".
echo   This is normal and only happens once.
echo.

:: ============================================================================
::  [Step 1 of 4] - Python and existing-environment check
:: ============================================================================
:: Prefer an already-healthy venv on a normal repeat launch: if .venv is
:: complete and on a compatible Python, no system Python is needed at all.
echo [Step 1 of 4] Checking Python and the project environment...
call :check_venv_complete
if defined VENV_COMPLETE (
    echo   Existing project environment looks good - reusing it.
) else (
    :: The venv must be (re)built, so a compatible system Python is required.
    call :ensure_build_python
    if defined FATAL exit /b 1
    echo   Using Python command: !PYTHON_CMD!
)

:: ============================================================================
::  [Step 2 of 4] - Virtual environment (self-healing)
:: ============================================================================
echo [Step 2 of 4] Setting up the virtual environment...
if defined VENV_COMPLETE (
    echo   Reusing the existing virtual environment.
) else (
    call :build_venv
    if defined FATAL exit /b 1
)

:: Activate the venv so "python" / "pythonw" below are the project's own.
call "%VENV_ACTIVATE%"
if not exist "%VENV_ACTIVATE%" (
    echo   ERROR: Virtual environment activation script missing after setup.
    pause
    exit /b 1
)

:: ============================================================================
::  [Step 3 of 4] - Dependencies (idempotent, health-gated)
:: ============================================================================
:: Only skip the install when the environment is provably healthy: a matching
:: requirements lock, "pip check" clean, and the required packages importable.
echo [Step 3 of 4] Checking dependencies...
call :check_deps_ok
if defined DEPS_OK (
    echo   Dependencies are already installed and healthy - skipping install.
    goto :deps_done
)
if not exist "%REQUIREMENTS%" (
    echo   Note: No requirements.txt at %REQUIREMENTS% - skipping dependencies.
    goto :deps_done
)
echo   Installing dependencies into the project environment...
python -m pip install --upgrade pip >nul 2>&1
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
:: Validate the freshly-installed environment BEFORE trusting it.
python -m pip check >nul 2>&1
if !errorlevel! neq 0 (
    echo   ERROR: The environment failed its health check ^(pip check^) after install.
    echo   Close this window and run this file again.
    pause
    exit /b 1
)
python -c "import pdfplumber, reportlab" >nul 2>&1
if !errorlevel! neq 0 (
    echo   ERROR: A required component could not be imported after install.
    echo   Close this window and run this file again.
    pause
    exit /b 1
)
:: Write the lock ONLY after a successful install AND a passing health check.
copy /y "%REQUIREMENTS%" "%LOCK%" >nul 2>&1
:deps_done

:: ============================================================================
::  [Step 4 of 4] - Preflight, then launch the GUI
:: ============================================================================
echo [Step 4 of 4] Starting %PROJECT_NAME%...
if not exist "%MAIN_SCRIPT%" (
    echo   ERROR: Main script not found: %MAIN_SCRIPT%
    echo   Please reinstall the program from a fresh copy of the release.
    pause
    exit /b 1
)

:: Preflight with the CONSOLE interpreter so a fatal startup error is visible.
:: The GUI itself is launched with pythonw (no console), which would otherwise
:: hide a crash from a non-technical user.
echo   Checking the program can start...
python "%MAIN_SCRIPT%" --check
if !errorlevel! neq 0 (
    echo.
    echo   The program could not start. The details are shown above.
    echo   Close this window and run this file again, or ask for help with
    echo   the message shown above.
    echo.
    pause
    exit /b 1
)

echo   Launching %PROJECT_NAME%...
if exist "%VENV_PYW%" (
    start "" pythonw "%MAIN_SCRIPT%"
) else (
    start "" python "%MAIN_SCRIPT%"
)

echo.
echo   %PROJECT_NAME% is starting in its own window. You can close this window.
pause
endlocal
exit /b 0


:: ============================================================================
::  Helpers
:: ============================================================================

:: ----------------------------------------------------------------------------
:: check_venv_complete - VENV_COMPLETE=1 if .venv exists, has an interpreter, and
:: that interpreter meets the minimum version. (Deps freshness is separate.)
:: ----------------------------------------------------------------------------
:check_venv_complete
set "VENV_COMPLETE="
if not exist "%VENV_ACTIVATE%" goto :eof
if not exist "%VENV_PY%" goto :eof
"%VENV_PY%" -c "import sys; sys.exit(0 if sys.version_info >= (%PY_MIN_MAJOR%, %PY_MIN_MINOR%) else 1)" >nul 2>&1
if errorlevel 1 goto :eof
set "VENV_COMPLETE=1"
goto :eof

:: ----------------------------------------------------------------------------
:: check_deps_ok - DEPS_OK=1 only if the venv is provably healthy: the lock
:: matches requirements.txt, "pip check" is clean, and imports succeed.
:: (Run after the venv is activated so "python" is the venv interpreter.)
:: ----------------------------------------------------------------------------
:check_deps_ok
set "DEPS_OK="
if not exist "%LOCK%" goto :eof
if not exist "%REQUIREMENTS%" goto :eof
fc /b "%LOCK%" "%REQUIREMENTS%" >nul 2>&1
if errorlevel 1 goto :eof
python -m pip check >nul 2>&1
if errorlevel 1 goto :eof
python -c "import pdfplumber, reportlab" >nul 2>&1
if errorlevel 1 goto :eof
set "DEPS_OK=1"
goto :eof

:: ----------------------------------------------------------------------------
:: ensure_build_python - find a system Python able to build the venv; install it
:: (with consent) if missing; STOP (FATAL) if it is missing or below the floor.
:: ----------------------------------------------------------------------------
:ensure_build_python
call :detect_python
if not defined PYTHON_OK (
    echo.
    echo   Python is not installed on this PC, and it is required to run this
    echo   program. This is the ONLY tool that has to be installed onto the
    echo   computer itself - everything else stays in this folder.
    echo.
    set "do_py="
    set /p do_py=Install Python now? ^(Y/N^):
    if /i "!do_py!"=="Y" (
        call :choose_scope
        call :install_python
        call :detect_python
    ) else (
        echo.
        echo   Python is required. You can install it manually from
        echo     https://www.python.org/downloads/
        echo   During install, check "Add python.exe to PATH", then run this
        echo   file again.
        echo.
        pause
        set "FATAL=1"
        goto :eof
    )
    if not defined PYTHON_OK (
        echo.
        echo   Python was installed but isn't visible in THIS window yet.
        echo   Close this window, re-open it, and run this file again so the
        echo   updated PATH takes effect.
        echo.
        pause
        set "FATAL=1"
        goto :eof
    )
)
:: HARD version gate on the interpreter that will build the venv: STOP, not warn.
for /f "tokens=2,3 delims=. " %%a in ('!PYTHON_CMD! --version 2^>^&1') do (
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
    set "FATAL=1"
)
goto :eof

:: ----------------------------------------------------------------------------
:: detect_python - PYTHON_OK / PYTHON_CMD for a usable system Python.
:: Prefers the "py" launcher (most reliable on Windows), then bare "python".
:: ----------------------------------------------------------------------------
:detect_python
set "PYTHON_OK="
set "PYTHON_CMD="
py -%PY_MIN_MAJOR% --version >nul 2>&1
if !errorlevel! equ 0 (
    set "PYTHON_CMD=py -%PY_MIN_MAJOR%"
    set "PYTHON_OK=1"
    goto :eof
)
python --version >nul 2>&1
if !errorlevel! equ 0 (
    set "PYTHON_CMD=python"
    set "PYTHON_OK=1"
)
goto :eof

:: ----------------------------------------------------------------------------
:: build_venv - rebuild an incomplete .venv from scratch (self-healing), with a
:: clear message for the Windows "a previous run still holds .venv open" case.
:: ----------------------------------------------------------------------------
:build_venv
if exist "%VENV_DIR%\" (
    echo   The existing environment is incomplete or outdated - rebuilding it...
    rmdir /s /q "%VENV_DIR%" >nul 2>&1
    if exist "%VENV_DIR%\" (
        echo.
        echo   ERROR: Could not remove the old .venv folder. A previous run may
        echo   still be using it. Please close any program windows opened from
        echo   this folder, check Task Manager for stray python.exe / pythonw.exe,
        echo   then run this file again.
        echo.
        pause
        set "FATAL=1"
        goto :eof
    )
) else (
    echo   Creating a fresh virtual environment in this folder...
)
!PYTHON_CMD! -m venv "%VENV_DIR%"
if !errorlevel! neq 0 (
    echo   ERROR: Failed to create the virtual environment.
    pause
    set "FATAL=1"
    goto :eof
)
if not exist "%VENV_ACTIVATE%" (
    echo   ERROR: The virtual environment looks broken after creation.
    pause
    set "FATAL=1"
)
goto :eof

:: ----------------------------------------------------------------------------
:: choose_scope - user vs machine scope. ONLY called for a forced install.
:: ----------------------------------------------------------------------------
:choose_scope
echo.
echo ----------------------------------------
echo   This install has to go onto the PC itself. Where should it go?
echo.
echo     1. Just for me     (no admin rights needed - safest at work)
echo     2. For all users   (requires admin rights on this PC)
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

:: ----------------------------------------------------------------------------
:: install_python - install Python via winget at the chosen scope (with consent).
:: ----------------------------------------------------------------------------
:install_python
echo   Installing Python (%INSTALL_SCOPE% scope)...
where winget >nul 2>&1
if %errorlevel% neq 0 (
    echo   Windows Package Manager ^(winget^) is not available on this PC.
    echo   Please install Python manually from:
    echo     https://www.python.org/downloads/
    echo   During install, check "Add python.exe to PATH", then run this file again.
    echo.
    pause
    goto :eof
)
if /i "%INSTALL_SCOPE%"=="machine" (
    winget install --id %PYTHON_WINGET_ID% --scope machine --accept-source-agreements --accept-package-agreements
) else (
    winget install --id %PYTHON_WINGET_ID% --scope user --accept-source-agreements --accept-package-agreements
)
goto :eof
