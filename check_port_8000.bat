@echo off
chcp 65001 >nul
echo ========================================
echo 检查端口 8000 占用情况
echo ========================================
echo.

netstat -ano | findstr :8000

echo.
echo ========================================
echo 如果看到 LISTENING 状态，说明端口被占用
echo 进程 ID 在最后一列
echo ========================================
echo.
echo 要关闭占用端口的进程，使用：
echo   taskkill /PID <进程ID> /F
echo.
pause

