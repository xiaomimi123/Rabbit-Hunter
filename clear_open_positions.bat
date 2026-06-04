@echo off
REM 清理数据库中的 OPEN 持仓记录
REM 
REM 用途：当币安测试网已全部平仓，但数据库中仍有 OPEN 状态的持仓时
REM 将这些持仓更新为 CLOSED 状态，以便重新测试

REM 设置编码为 UTF-8
chcp 65001 >nul

REM 切换到脚本目录
cd /d "%~dp0"

echo ========================================
echo 清理数据库中的 OPEN 持仓记录
echo ========================================
echo.

REM 检查 Python
set PYTHON_CMD=
py --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PYTHON_CMD=py
) else (
    python --version >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        set PYTHON_CMD=python
    ) else (
        echo [ERROR] 未找到 Python，请先安装 Python
        pause
        exit /b 1
    )
)

REM 运行清理脚本
echo 正在运行清理脚本...
echo.
%PYTHON_CMD% scripts\clear_open_positions.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] 清理失败，请检查错误信息
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ========================================
echo 清理完成
echo ========================================
pause

