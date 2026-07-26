@echo off
setlocal
cd /d "%~dp0"

set "VENV_DIR=%~dp0App\.venv"
set "PY=%VENV_DIR%\Scripts\python.exe"

where python >nul 2>nul
if errorlevel 1 (
    echo Python not found. Please install Python 3.10 or newer, and check "Add to PATH" during setup.
    echo Download: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

if not exist "%PY%" (
    echo First run: creating a local virtual environment, please wait...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo Failed to create virtual environment. Please check your Python installation.
        pause
        exit /b 1
    )
)

"%PY%" "%~dp0App\launcher.py" %*
if errorlevel 1 (
    echo.
    pause
)

endlocal
