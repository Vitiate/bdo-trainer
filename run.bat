@echo off
setlocal EnableDelayedExpansion
REM BDO Trainer — Windows run script.
REM
REM Picks a known-good Python version, creates / refreshes the venv,
REM installs requirements, and launches main.py.
REM
REM Preference order: py -3.13 → py -3.12 → py -3.11 → 'python'.
REM On Windows the input hooks don't have the macOS pyobjc bug, but
REM newer Python releases occasionally lack pre-built wheels, so we
REM still bias toward the LTS-ish minor versions.

REM --- Request admin (input hooks need it while BDO is running) -------------
net session >nul 2>&1
if errorlevel 1 (
    echo Requesting administrator privileges...
    powershell -Command "Start-Process -Verb RunAs -FilePath '%~f0' -WorkingDirectory '%~dp0'"
    exit /b
)

cd /d "%~dp0"

echo ========================================
echo BDO Trainer - Starting Application (Admin)
echo ========================================
echo.

REM --- Python detection -----------------------------------------------------
REM We check the py launcher (`py -3.13`) first because it's the
REM canonical way to pin a minor version on Windows. Then fall back
REM to `python` on PATH.
set "PYCMD="
for %%V in (3.13 3.12 3.11) do (
    if not defined PYCMD (
        py -%%V --version >nul 2>&1
        if not errorlevel 1 (
            set "PYCMD=py -%%V"
        )
    )
)

if not defined PYCMD (
    python --version >nul 2>&1
    if not errorlevel 1 (
        set "PYCMD=python"
    )
)

if not defined PYCMD (
    echo ERROR: No Python 3 interpreter found.
    echo.
    echo Install Python 3.13 ^(recommended^), 3.12, or 3.11 from
    echo https://www.python.org/ — make sure to tick "Add to PATH"
    echo during the installer.
    pause
    exit /b 1
)

for /f "tokens=*" %%V in ('%PYCMD% --version 2^>^&1') do set "PYVERSION=%%V"
echo Python found: %PYCMD% ^(%PYVERSION%^)
echo.

REM Pick up the X.Y portion of the version for the venv-recreation check.
for /f "tokens=*" %%V in ('%PYCMD% -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set "PY_MAJOR_MINOR=%%V"

REM --- venv selection / recreation -----------------------------------------
set "VENV_DIR="
if exist ".venv\Scripts\activate.bat" set "VENV_DIR=.venv"
if not defined VENV_DIR (
    if exist "venv\Scripts\activate.bat" set "VENV_DIR=venv"
)

REM If existing venv's Python doesn't match the one we'd pick now,
REM recreate. Same logic as run.sh.
if defined VENV_DIR (
    for /f "tokens=*" %%V in ('"%VENV_DIR%\Scripts\python.exe" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set "VENV_VERSION=%%V"
    if not "!VENV_VERSION!"=="%PY_MAJOR_MINOR%" (
        echo Existing venv uses Python !VENV_VERSION! but %PY_MAJOR_MINOR% is preferred.
        echo Recreating %VENV_DIR%\ ...
        rmdir /s /q "%VENV_DIR%"
        set "VENV_DIR="
    )
)

if not defined VENV_DIR (
    echo Creating virtual environment with %PYCMD% ...
    set "VENV_DIR=.venv"
    %PYCMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Virtual environment created at %VENV_DIR%\.
    echo.
)

REM --- Activate -------------------------------------------------------------
echo Activating virtual environment...
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment.
    pause
    exit /b 1
)

REM --- tkinter check --------------------------------------------------------
python -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo ERROR: tkinter not available. The Python installer should bundle
    echo it; reinstall Python from https://www.python.org/ and tick the
    echo "tcl/tk and IDLE" component.
    pause
    exit /b 1
)

REM --- Install / update requirements ---------------------------------------
if exist "requirements.txt" (
    echo Installing / updating dependencies...
    pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo WARNING: Some dependencies may not have installed correctly.
    )
)

echo.
echo ========================================
echo Starting BDO Trainer...
echo ========================================
echo.

python main.py %*

if errorlevel 1 (
    echo.
    echo ========================================
    echo Application exited with an error
    echo ========================================
    pause
    exit /b 1
)

echo.
echo ========================================
echo Application closed successfully
echo ========================================
pause
