@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo Rabbit Hunter FastAPI 后端服务
echo ========================================
echo [INFO] 当前目录: %CD%
echo [INFO] 开始启动 API 服务...
echo.

set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if "%PY_CMD%"=="" (
  where python >nul 2>nul && set "PY_CMD=python"
)
if "%PY_CMD%"=="" (
  echo [ERROR] 未找到 Python（python/py 命令不存在）。请安装 Python 3，并勾选"Add to PATH"。
  pause
  exit /b 9009
)

echo [INFO] 使用 Python 命令: %PY_CMD%
echo [INFO] 服务地址: http://localhost:8000
echo [INFO] API 文档: http://localhost:8000/docs
echo [INFO] 按 Ctrl+C 停止服务
echo.
echo ========================================
echo.

REM 检查端口是否被占用
echo [INFO] 检查端口 8000...
netstat -ano | findstr :8000 | findstr LISTENING >nul
if %ERRORLEVEL% EQU 0 (
    echo [WARNING] 端口 8000 已被占用！
    echo.
    echo 请选择：
    echo   1. 关闭占用端口的进程（运行 kill_port_8000.bat）
    echo   2. 使用其他端口启动服务
    echo.
    set /p choice="是否尝试关闭占用端口的进程？(Y/N): "
    if /i "!choice!"=="Y" (
        call kill_port_8000.bat
        timeout /t 2 >nul
    ) else (
        echo [INFO] 跳过端口检查，继续启动...
    )
)

echo.
echo [INFO] 启动 FastAPI 服务...
echo.

REM 启动服务
%PY_CMD% -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================
    echo [ERROR] 服务启动失败，错误代码: %ERRORLEVEL%
    echo ========================================
    echo.
    echo 可能的原因：
    echo 1. 端口 8000 已被占用
    echo 2. 依赖未安装（运行: pip install -r requirements.txt）
    echo 3. 环境变量未配置（检查 .env 文件）
    echo.
    pause
)

