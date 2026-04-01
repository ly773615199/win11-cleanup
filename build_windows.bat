@echo off
:: ═══════════════════════════════════════════════════════
::  Win11 垃圾清理工具 - Windows 一键打包脚本
::  双击运行，自动编译为单个 EXE 文件
:: ═══════════════════════════════════════════════════════

title Win11 Cleanup - EXE 打包工具
echo.
echo ╔══════════════════════════════════════════════╗
echo ║   🔨  Win11 Cleanup EXE 打包工具            ║
echo ╚══════════════════════════════════════════════╝
echo.

:: 检查 Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 未检测到 Python！
    echo.
    echo 请先安装 Python 3.8+: https://www.python.org/downloads/
    echo 安装时勾选 "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

:: 检查 PyInstaller
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo 📦 正在安装 PyInstaller...
    pip install pyinstaller --quiet
    if %errorlevel% neq 0 (
        echo ❌ PyInstaller 安装失败
        pause
        exit /b 1
    )
)

:: 切换到脚本目录
cd /d "%~dp0"

echo 🔨 正在编译 EXE...
echo    这可能需要 1-3 分钟，请耐心等待
echo.

:: 清理旧的构建
if exist build rd /s /q build
if exist dist rd /s /q dist
if exist "*.spec" del /q "*.spec"

:: 编译
python -m PyInstaller ^
    --onefile ^
    --name "Win11Cleanup" ^
    --icon "NONE" ^
    --clean ^
    --noconfirm ^
    --console ^
    --add-data "README.md;." ^
    win11_cleanup.py

if %errorlevel% neq 0 (
    echo.
    echo ❌ 编译失败！
    pause
    exit /b 1
)

:: 清理中间文件
if exist build rd /s /q build
if exist "*.spec" del /q "*.spec"

:: 结果
echo.
echo ═══════════════════════════════════════════════
echo ✅ 编译成功！
echo.
echo 📁 输出文件: dist\Win11Cleanup.exe
echo.

:: 显示文件大小
for %%A in (dist\Win11Cleanup.exe) do echo    文件大小: %%~zA bytes

echo.
echo 💡 使用方法:
echo    双击 dist\Win11Cleanup.exe 即可运行
echo    建议右键 - 以管理员身份运行
echo ═══════════════════════════════════════════════
echo.

:: 询问是否打开输出目录
set /p open="是否打开输出目录? (y/n): "
if /i "%open%"=="y" explorer dist

pause
