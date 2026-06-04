@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Rabbit Hunter - Collector

echo ============================================================
echo   Rabbit Hunter v5.0  Collector + AI Trading
echo ============================================================
echo.
echo   MarketScanner  -^> DeepCollector  -^> StrategyScorer
echo   OpenAI GPT-4o  -^> BinanceTrader
echo.
echo   Press Ctrl+C to stop
echo ============================================================
echo.

set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if "%PY_CMD%"=="" (
  where python >nul 2>nul && set "PY_CMD=python"
)
if "%PY_CMD%"=="" (
  echo [ERROR] 未找到 Python，请安装 Python 3 并勾选 "Add to PATH"
  pause
  exit /b 1
)

%PY_CMD% -m scripts.tasks.collector_main

if %ERRORLEVEL% NEQ 0 (
  echo.
  echo [ERROR] 采集器退出，错误代码: %ERRORLEVEL%
  pause
)

