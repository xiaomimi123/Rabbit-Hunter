@echo off
chcp 65001 >nul
echo ========================================
echo 关闭占用端口 8000 的进程
echo ========================================
echo.

REM 查找占用 8000 端口的进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo 找到进程 ID: %%a
    echo 正在关闭...
    taskkill /PID %%a /F >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo [成功] 进程 %%a 已关闭
    ) else (
        echo [失败] 无法关闭进程 %%a（可能需要管理员权限）
    )
)

echo.
echo ========================================
echo 检查完成
echo ========================================
echo.
timeout /t 3 >nul

