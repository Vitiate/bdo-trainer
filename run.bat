@echo off
REM BDO Trainer - Windows Run Script
REM This script runs the BDO Trainer application

REM --- Request admin privileges (required for input hooks while BDO is running) ---
net session >nul 2>&1
if errorlevel 1 (
    echo Requesting administrator privileges...
    powershell -Command "Start-Process -Verb RunAs -FilePath '%~f0' -WorkingDirectory '%~dp0'"
    exit /b
)

REM Ensure working directory is the script's folder (after elevation)
cd /d "%~dp0"

echo ========================================
echo BDO Trainer - Starting Application (Admin)
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher from https://www.python.org/
    pause
    exit /b 1
)

echo Python found!
echo.

REM Check if virtual environment exists
if not exist "venv\" (
    echo Virtual environment not found. Creating one...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo Virtual environment created successfully!
    echo.
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment
    pause
    exit /b 1
)

REM Check if dependencies are installed
echo Checking dependencies...
python -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo ERROR: tkinter is not available. Please install python-tk
    pause
    exit /b 1
)

REM Install/update requirements if needed
if exist "requirements.txt" (
    echo Installing/updating dependencies from requirements.txt...
    pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo WARNING: Some dependencies may not have installed correctly
    )
)

echo.
echo ========================================
echo Starting BDO Trainer...
echo ========================================
echo.

REM Run the application
python main.py

REM Check exit code
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
