@echo off
chcp 65001 >nul
title Rabbit Hunter v5.0 - 完整启动

echo.
echo ============================================================
echo   Rabbit Hunter v5.0 - 完整启动 (多窗口模式)
echo ============================================================
echo.
echo 此脚本将在多个窗口启动：
echo   1. FastAPI 后端 (http://localhost:8000)
echo   2. 数据采集器 (Python 脚本)
echo   3. 前端 V4.3 (http://localhost:5173)
echo.
echo ============================================================
echo.

REM 获取脚本目录
set "SCRIPT_DIR=%~dp0"

REM 检查必要文件
if not exist "%SCRIPT_DIR%start_api.bat" (
    echo [ERROR] 未找到 start_api.bat
    pause
    exit /b 1
)

if not exist "%SCRIPT_DIR%start_frontend.bat" (
    echo [ERROR] 未找到 start_frontend.bat
    pause
    exit /b 1
)

if not exist "%SCRIPT_DIR%start_collector.bat" (
    echo [ERROR] 未找到 start_collector.bat
    pause
    exit /b 1
)

REM 启动后端
echo [1/3] 启动 FastAPI 后端服务...
start "Rabbit Hunter Backend" /d "%SCRIPT_DIR%" cmd /c start_api.bat

REM 等待后端启动
timeout /t 3 >nul

REM 启动采集器
echo [2/3] 启动数据采集器...
start "Rabbit Hunter Collector" /d "%SCRIPT_DIR%" cmd /c start_collector.bat

REM 等待采集器启动
timeout /t 2 >nul

REM 启动前端
echo [3/3] 启动前端 V4.3 (Vite)...
start "Rabbit Hunter Frontend V4.3" /d "%SCRIPT_DIR%" cmd /c start_frontend.bat

echo.
echo ============================================================
echo ✅ 所有服务已启动！
echo ============================================================
echo.
echo 访问地址：
echo   前端:     http://localhost:5173
echo   API 文档: http://localhost:8000/docs
echo.
echo 已在 3 个独立窗口中启动：
echo   FastAPI 后端 (localhost:8000)
echo   数据采集器 + OpenAI AI 层
echo   前端 (localhost:5173)
echo.
echo 按 Ctrl+C 关闭任何窗口，或直接关闭所有窗口即可停止所有服务。
echo.
pause

