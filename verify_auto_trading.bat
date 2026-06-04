@echo off
REM 自动交易功能验证脚本
REM 
REM 用于快速检查自动交易功能的配置和状态

chcp 65001 >nul
echo ========================================
echo Rabbit Hunter V4.5 自动交易功能验证
echo ========================================
echo.

REM 切换到脚本目录
cd /d "%~dp0"

REM 检查 Python（尝试多种命令）
set PYTHON_CMD=
set PYTHON_FOUND=0

REM 尝试 py launcher（Windows Python Launcher，最可靠）
py --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PYTHON_CMD=py
    set PYTHON_FOUND=1
    echo [INFO] 找到 Python: py
    py --version
) else (
    REM 尝试 python 命令
    python --version >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set PYTHON_CMD=python
        set PYTHON_FOUND=1
        echo [INFO] 找到 Python: python
        python --version
    ) else (
        REM 尝试 python3
        python3 --version >nul 2>&1
        if %ERRORLEVEL% EQU 0 (
            set PYTHON_CMD=python3
            set PYTHON_FOUND=1
            echo [INFO] 找到 Python: python3
            python3 --version
        )
    )
)

if %PYTHON_FOUND% EQU 0 (
    echo [ERROR] 未找到 Python
    echo.
    echo 请尝试以下方法：
    echo   1. 确保 Python 已安装
    echo   2. 将 Python 添加到系统 PATH
    echo   3. 或使用 Windows Python Launcher (py)
    echo.
    echo 如果已安装 Python，可以手动运行：
    echo   py scripts\verify_auto_trading.py
    echo   或
    echo   python scripts\verify_auto_trading.py
    pause
    exit /b 1
)

REM 运行验证脚本
echo.
echo 正在运行验证脚本...
echo 使用命令: %PYTHON_CMD% scripts\verify_auto_trading.py
echo.
%PYTHON_CMD% scripts\verify_auto_trading.py

if errorlevel 1 (
    echo.
    echo [ERROR] 验证脚本执行失败
    echo 错误代码: %ERRORLEVEL%
    echo.
    echo 请检查：
    echo   1. Python 是否正确安装
    echo   2. 项目依赖是否已安装（pip install -r requirements.txt）
    echo   3. .env 文件是否配置正确
    echo.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ========================================
echo 验证完成
echo ========================================
pause

