@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo 币安测试网 API 验证工具
echo ========================================
echo.
echo 此工具将直接测试币安测试网 API Key 和 Secret
echo 绕过 CCXT 库，直接调用币安 API
echo.
echo 用法:
echo   test_binance_testnet.bat <api_key> <api_secret>
echo.
echo 或从配置管理器读取（如果已配置）:
echo   test_binance_testnet.bat
echo.
echo ========================================
echo.

set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if "%PY_CMD%"=="" (
  where python >nul 2>nul && set "PY_CMD=python"
)
if "%PY_CMD%"=="" (
  echo [ERROR] 未找到 Python
  pause
  exit /b 9009
)

echo [INFO] 使用 Python 命令: %PY_CMD%
echo.

if "%1"=="" (
    echo [INFO] 从配置管理器读取配置...
    %PY_CMD% scripts\test_binance_api.py
) else (
    echo [INFO] 使用命令行参数...
    %PY_CMD% scripts\test_binance_api.py %1 %2
)

echo.
pause

