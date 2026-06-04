@echo off
chcp 65001 >nul
echo ========================================
echo Rabbit Hunter V4.3 前端 (Vite)
echo ========================================
echo [INFO] 当前目录: %CD%
echo [INFO] 开始启动前端服务...
echo.

REM 切换到新的前端目录
cd /d "%~dp0\Rabbit Hunterfronted"

REM 检查 node_modules 是否存在
if not exist "node_modules" (
    echo [INFO] node_modules 未找到，正在安装依赖...
    call npm install
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] 依赖安装失败
        pause
        exit /b %ERRORLEVEL%
    )
)

REM 启动前端
echo [INFO] 服务地址: http://localhost:5173
echo [INFO] 按 Ctrl+C 停止服务
echo.
echo ========================================
echo.

call npm run dev

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================
    echo [ERROR] 前端启动失败，错误代码: %ERRORLEVEL%
    echo ========================================
    echo.
    echo 可能的原因：
    echo 1. 依赖未安装（运行: npm install）
    echo 2. 端口 5173 已被占用
    echo.
    pause
)

