@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title Web Novel Editor
chcp 65001 >nul 2>&1
set "PYTHONIOENCODING=utf-8"

:: ============================================================================
::  Web Novel Editor  --  Windows setup + launcher (double-click this file)
:: ============================================================================
::  [Step 1 of 3] A healthy project environment (.venv) is checked offline and the
::                program starts immediately. No internet, no installs.
::  [Step 2 of 3] Otherwise a separate Python 3.10+ is located (never the Microsoft
::                Store alias). If none exists you are asked before anything is
::                installed, and only for your user account.
::  [Step 3 of 3] scripts\bootstrap.py repairs or rebuilds .venv, installs the
::                exact pinned packages (this may need internet), proves the
::                environment healthy and starts the program.
::  Re-running this file is always the repair path. Setup logs are kept in
::  files\runtime-data\logs. No system settings or PATH entries are changed.
:: ============================================================================

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "BOOTSTRAP=%~dp0scripts\bootstrap.py"
set "LOG_DIR=%~dp0files\runtime-data\logs"
set "PYTHON_WINGET_ID=Python.Python.3.13"
set "PYTHON_URL=https://www.python.org/downloads/"
set "BASE_PY="
set "RC=0"

echo ============================================================
echo   Web Novel Editor - Setup and Launcher
echo   Folder: %CD%
echo ============================================================
echo.
echo   First-run note: if Windows SmartScreen warns about this file,
echo   choose "More info" and then "Run anyway". This only happens once.
echo.

if exist "%BOOTSTRAP%" goto have_bootstrap
echo ERROR: The setup helper is missing: %BOOTSTRAP%
echo Please download a fresh copy of the program.
set "RC=10"
goto hold

:have_bootstrap
if not exist "%VENV_PY%" goto setup
echo [Step 1 of 3] Checking the existing program environment (offline)...
"%VENV_PY%" "%BOOTSTRAP%" --launch-only
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" goto done
if "%RC%"=="4" goto launch_failed
echo   Setup or repair is needed.

:setup
echo.
echo [Step 2 of 3] Looking for Python 3.10 or newer...
call :find_python
if defined BASE_PY goto run_setup
if exist "%VENV_PY%" goto run_setup_inside
call :offer_python_install
call :find_python
if defined BASE_PY goto run_setup
goto no_python

:run_setup
echo   Using Python: %BASE_PY%
echo.
echo [Step 3 of 3] Setting up and starting (the first time can take a few minutes)...
"%BASE_PY%" "%BOOTSTRAP%"
set "RC=%ERRORLEVEL%"
goto after_setup

:run_setup_inside
echo   No separate Python was found; repairing in place with the existing environment.
echo.
echo [Step 3 of 3] Repairing and starting...
"%VENV_PY%" "%BOOTSTRAP%"
set "RC=%ERRORLEVEL%"

:after_setup
if "%RC%"=="0" goto done
if "%RC%"=="2" goto cancelled
if "%RC%"=="4" goto launch_failed
echo.
echo ERROR: Setup did not complete (code %RC%). The message above explains why.
echo Logs are in: %LOG_DIR%
goto hold

:no_python
echo.
echo   Python 3.10 or newer is required and was not found.
echo   Install it from %PYTHON_URL%
echo   (tick "Add python.exe to PATH" during installation), then run this file again.
set "RC=10"
goto hold

:cancelled
echo.
echo Setup was cancelled. Nothing else was changed.
goto hold

:launch_failed
echo.
echo ERROR: Web Novel Editor could not start. The details are shown above.
echo Logs are in: %LOG_DIR%
goto hold

:done
echo.
echo   Web Novel Editor is running in its own window. You can close this window.

:hold
echo.
set "CLOSE_ANSWER="
set /p "CLOSE_ANSWER=Press Enter to close this window..."
exit /b %RC%


:: ============================================================================
::  Helpers
:: ============================================================================

:: find_python - BASE_PY = first Python 3.10+ that is not a Store alias.
:find_python
set "BASE_PY="
for /f "delims=" %%L in ('where py 2^>nul') do if not defined BASE_PY call :try_py_launcher "%%L"
if defined BASE_PY goto :eof
if defined LOCALAPPDATA for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if not defined BASE_PY call :try_python "%%D\python.exe"
if defined ProgramFiles for /d %%D in ("%ProgramFiles%\Python3*") do if not defined BASE_PY call :try_python "%%D\python.exe"
for /f "delims=" %%P in ('where python 2^>nul') do if not defined BASE_PY call :try_python "%%P"
goto :eof

:: try_py_launcher "path" - ask a py launcher (never one inside WindowsApps) for its Python 3.
:try_py_launcher
set "PY_LAUNCHER=%~1"
echo "%PY_LAUNCHER%" | find /i "\WindowsApps\" >nul
if not errorlevel 1 goto :eof
for /f "delims=" %%E in ('call "%PY_LAUNCHER%" -3 -c "import sys; print(sys.executable)" 2^>nul') do if not defined BASE_PY call :try_python "%%E"
goto :eof

:: try_python "path" - accept only an existing, non-Store interpreter that runs and is 3.10+.
:try_python
set "CANDIDATE=%~1"
if not exist "%CANDIDATE%" goto :eof
echo "%CANDIDATE%" | find /i "\WindowsApps\" >nul
if not errorlevel 1 goto :eof
"%CANDIDATE%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto :eof
set "BASE_PY=%CANDIDATE%"
goto :eof

:: offer_python_install - consent-gated, user-scope only. Never changes PATH itself.
:offer_python_install
echo.
echo   Python 3.10 or newer is needed to run Web Novel Editor and was not found.
echo   This is the only program installed outside this folder.
echo.
set "INSTALL_ANSWER="
set /p "INSTALL_ANSWER=Install Python 3.13 for your user account now with winget? (Y/N): "
if /i not "%INSTALL_ANSWER%"=="Y" goto :eof
where winget >nul 2>&1
if not errorlevel 1 goto run_winget
echo   Windows Package Manager (winget) is not available on this PC.
echo   Install Python from %PYTHON_URL% instead.
goto :eof
:run_winget
echo   Installing Python for the current user only (no administrator rights needed)...
winget install --id %PYTHON_WINGET_ID% --exact --scope user --accept-source-agreements --accept-package-agreements
goto :eof
