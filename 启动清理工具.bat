@echo off
:: Win11 垃圾清理工具 - 启动器
:: 双击运行，自动以管理员权限启动 PowerShell 脚本

title Win11 垃圾清理工具 v2.0

:: 检查管理员权限
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo 正在请求管理员权限...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: 切换到脚本目录
cd /d "%~dp0"

:: 运行 PowerShell 脚本
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0Win11Cleanup.ps1"

pause
