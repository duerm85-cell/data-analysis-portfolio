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

REM 优先使用系统 Anaconda3 环境（已安装所有依赖）
set PYTHON="C:\Users\Lenovo\anaconda3\python.exe"

if exist %PYTHON% (
    echo [OK] 找到 Python 环境
    echo [OK] 正在启动 Streamlit 应用 (projects/01-a-stock-quant-analysis/app_pro.py)
    echo.
    echo 浏览器访问: http://localhost:8501
    echo.
    %PYTHON% -m streamlit run app_pro.py --server.port 8501 --server.headless true
) else (
    echo [ERROR] 找不到 Python 环境
    echo 请确认 C:\Users\Lenovo\anaconda3\ 已正确安装
    pause
)