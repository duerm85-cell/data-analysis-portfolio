@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM ================================================================
REM   启动路径兼容性：
REM   run_app.bat 位于 projects/01-a-stock-quant-analysis/ 子目录
REM   %~dp0 已经保证切到脚本所在目录，所以 app_pro.py 是当前目录下的
REM ================================================================

echo ========================================
echo   A股量化选股分析系统 启动中...
echo   脚本目录: %~dp0
echo ========================================
echo.

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"

%PYTHON_EXE% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 找不到 Python。请安装 Python 3.10+ 或在项目目录创建 .venv。
    pause
    exit /b 1
)

echo [OK] 正在启动 Streamlit 应用
echo 浏览器访问: http://localhost:8501
echo.
%PYTHON_EXE% -m streamlit run app_pro.py --server.port 8501 --server.headless true
