@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   A股量化选股分析系统 启动中...
echo ========================================
echo.

REM 优先使用系统 Anaconda3 环境（已安装所有依赖）
set PYTHON="C:\Users\Lenovo\anaconda3\python.exe"

if exist %PYTHON% (
    echo [OK] 找到 Python 环境
    echo [OK] 正在启动 Streamlit 应用...
    echo.
    %PYTHON% -m streamlit run app_pro.py --server.port 8501 --server.headless true
) else (
    echo [ERROR] 找不到 Python 环境
    echo 请确认 C:\Users\Lenovo\anaconda3\ 已正确安装
    pause
)