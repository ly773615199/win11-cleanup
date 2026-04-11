@echo off
setlocal enabledelayedexpansion

:: 停止 Windows Update 服务
net stop wuauserv /y >nul 2>&1

:: 定义要清理的目录路径
set "directories=%TEMP%\* C:\Windows\Temp\* %SystemRoot%\memory.dmp %SystemRoot%\Minidump\* C:\Windows\SoftwareDistribution\Download\* C:\Windows\System32\LogFiles\Sum\ApiLogFile\* C:\Windows\System32\LogFiles\Sum\ApiLogFiles\Archive\* C:\Windows\Logs\CBS\CBS.log C:\Windows\Logs\MoSetup\*.log C:\Windows\Panther\UnattendGC\* C:\Windows\panther\setuperr.log C:\Windows\panther\setupact.log C:\Windows\Winsxs\ManifestCache\* C:\Windows\Prefetch\* C:\Windows\SoftwareDistribution\DataStore\*"

:: 清理指定目录下的所有文件和子目录
for %%D in (%directories%) do (
    if exist "%%D" (
        echo 正在清理: %%D
        del /f /q /s "%%D" >nul 2>&1
        for /d %%X in ("%%D") do @rd /s /q "%%X" >nul 2>&1
    )
)

:: 启动 Windows Update 服务
net start wuauserv >nul 2>&1

:: 清空回收站
powershell -Command "Clear-RecycleBin -Confirm:$false -ErrorAction SilentlyContinue" >nul 2>&1

:: 清除事件日志
wevtutil el | ForEach-Object { wevtutil cl "$_" } >nul 2>&1

echo 深度清理完成！
pause