@echo off
setlocal
cd /d "%~dp0"

set "VENV_DIR=%~dp0App\.venv"
set "PY=%VENV_DIR%\Scripts\python.exe"

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10 及以上版本，并确保安装时勾选 "Add to PATH"。
    echo 下载地址: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

if not exist "%PY%" (
    echo [初始化] 首次运行，正在创建独立运行环境，请稍候...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败，请检查 Python 安装是否完整。
        pause
        exit /b 1
    )

    echo [初始化] 正在安装依赖库（python-docx, pypdf）...
    "%PY%" -m pip install --upgrade pip >nul
    "%PY%" -m pip install -r "%~dp0App\requirements.txt"
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络连接后重新运行本脚本。
        pause
        exit /b 1
    )
    echo [初始化] 环境准备完成。
    echo.
)

where ollama >nul 2>nul
if errorlevel 1 (
    echo [提示] 未检测到 Ollama。本程序需要本地 Ollama 提供翻译模型支持。
    echo        请前往 https://ollama.com/download 下载安装后，再重新启动本程序。
    echo.
)

"%PY%" "%~dp0App\engine\gui.py" %*
if errorlevel 1 (
    echo.
    echo [提示] 程序异常退出，请查看上方信息或 Data\logs 目录下的日志。
    pause
)

endlocal
