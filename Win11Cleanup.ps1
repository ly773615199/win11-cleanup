#Requires -Version 5.1
<# 
.SYNOPSIS
    Win11 垃圾清理工具 v2.0
.DESCRIPTION
    全面清理系统盘(C:)和数据盘(D:)的垃圾文件，释放磁盘空间
.NOTES
    以管理员身份运行效果最佳
#>

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# ─── 配置 ───────────────────────────────────────────────
$Script:TotalCleaned = 0
$Script:CleanedFiles = 0

# ─── 清理项定义 ─────────────────────────────────────────
$CleanupItems = @(
    @{ Name="系统临时文件";         Drive="C"; Path="$env:TEMP" },
    @{ Name="Windows临时文件";      Drive="C"; Path="C:\Windows\Temp" },
    @{ Name="Windows更新缓存";      Drive="C"; Path="C:\Windows\SoftwareDistribution\Download" },
    @{ Name="预取文件";             Drive="C"; Path="C:\Windows\Prefetch" },
    @{ Name="缩略图缓存";           Drive="C"; Path="$env:LOCALAPPDATA\Microsoft\Windows\Explorer" },
    @{ Name="Windows错误报告";      Drive="C"; Path="C:\ProgramData\Microsoft\Windows\WER" },
    @{ Name="DirectX着色器缓存";    Drive="C"; Path="$env:LOCALAPPDATA\D3DSCache" },
    @{ Name="临时互联网文件";       Drive="C"; Path="$env:LOCALAPPDATA\Microsoft\Windows\INetCache" },
    @{ Name="崩溃转储文件";         Drive="C"; Path="$env:LOCALAPPDATA\CrashDumps" },
    @{ Name="最近打开文件记录";     Drive="C"; Path="$env:APPDATA\Microsoft\Windows\Recent" },
    @{ Name="系统日志文件";         Drive="C"; Path="C:\Windows\Logs" },
    @{ Name="CBS日志";              Drive="C"; Path="C:\Windows\Logs\CBS" },
    @{ Name="安装程序日志";         Drive="C"; Path="C:\Windows\Panther" },
    @{ Name="Delivery优化文件";     Drive="C"; Path="C:\Windows\SoftwareDistribution\DeliveryOptimization" },
    @{ Name="NVIDIA着色器缓存";     Drive="C"; Path="$env:LOCALAPPDATA\NVIDIA\DXCache" },
    @{ Name="NVIDIA GLCache";       Drive="C"; Path="$env:LOCALAPPDATA\NVIDIA\GLCache" },
    @{ Name="回收站";               Drive="C"; Path="RecycleBin" },
    # D盘清理项
    @{ Name="[D盘]临时文件";        Drive="D"; Path="D:\Temp" },
    @{ Name="[D盘]系统映像缓存";    Drive="D"; Path="D:\$Recycle.Bin" },
    @{ Name="[D盘]Thumbs.db文件";   Drive="D"; Path="ThumbsDb" },
    @{ Name="[D盘]Desktop.ini文件"; Drive="D"; Path="DesktopIni" },
    @{ Name="[D盘]旧日志文件";      Drive="D"; Path="Logs" },
    @{ Name="[D盘]旧备份文件";      Drive="D"; Path="Backups" },
    @{ Name="[D盘]浏览器缓存";     Drive="D"; Path="BrowserCache" },
    @{ Name="[D盘]Steam缓存";       Drive="D"; Path="SteamCache" },
    @{ Name="[D盘]包管理器缓存";    Drive="D"; Path="PackageManager" },
)

# ─── 工具函数 ────────────────────────────────────────────

function Write-Colored {
    param([string]$Text, [string]$Color = "White")
    Write-Host $Text -ForegroundColor $Color
}

function Get-SizeString {
    param([long]$Bytes)
    if ($Bytes -ge 1GB) { return "{0:N2} GB" -f ($Bytes / 1GB) }
    elseif ($Bytes -ge 1MB) { return "{0:N2} MB" -f ($Bytes / 1MB) }
    elseif ($Bytes -ge 1KB) { return "{0:N2} KB" -f ($Bytes / 1KB) }
    else { return "$Bytes B" }
}

function Get-FolderSize {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return 0 }
    try {
        $size = (Get-ChildItem -Path $Path -Recurse -Force -ErrorAction SilentlyContinue | 
                 Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
        return [long]($size ?? 0)
    } catch { return 0 }
}

function Get-DriveFreeSpace {
    param([string]$Drive = "C:")
    try {
        $disk = Get-PSDrive -Name $Drive.TrimEnd(':') -ErrorAction Stop
        return $disk.Free
    } catch { return 0 }
}

function Test-IsAdmin {
    $current = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($current)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# ─── 清理函数 ────────────────────────────────────────────

function Clear-FolderContents {
    param([string]$Path, [string]$Filter = "*")
    $cleaned = 0
    if (-not (Test-Path $Path)) { return 0 }
    try {
        $items = Get-ChildItem -Path $Path -Filter $Filter -Recurse -Force -ErrorAction SilentlyContinue
        foreach ($item in $items) {
            try {
                $size = if ($item.PSIsContainer) { 0 } else { $item.Length }
                Remove-Item $item.FullName -Recurse -Force -ErrorAction SilentlyContinue
                $cleaned += $size
                $Script:CleanedFiles++
            } catch { }
        }
        # 清理空目录
        Get-ChildItem -Path $Path -Directory -Recurse -Force -ErrorAction SilentlyContinue | 
            Sort-Object { $_.FullName.Length } -Descending | 
            ForEach-Object { 
                try { 
                    if ((Get-ChildItem $_.FullName -Force -ErrorAction SilentlyContinue).Count -eq 0) {
                        Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue 
                    }
                } catch {} 
            }
    } catch { }
    return $cleaned
}

function Clear-RecycleBin {
    try {
        $shell = New-Object -ComObject Shell.Application
        $recycle = $shell.Namespace(0xA)
        if ($recycle) {
            $items = $recycle.Items()
            $count = $items.Count
            $shell.Namespace(0xA).Self.InvokeVerb("Empty Recycle &Bin")
        }
        return 0 # 无法精确计算
    } catch { return 0 }
}

function Clear-WindowsUpdateCache {
    # 停止服务 → 清理 → 重启服务
    try {
        Stop-Service -Name wuauserv -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
        $cleaned = Clear-FolderContents "C:\Windows\SoftwareDistribution\Download"
        Start-Service -Name wuauserv -ErrorAction SilentlyContinue
        return $cleaned
    } catch {
        Start-Service -Name wuauserv -ErrorAction SilentlyContinue
        return 0
    }
}

function Clear-DeliveryOptimization {
    try {
        # 清理 Delivery Optimization 缓存
        $cleaned = Clear-FolderContents "C:\Windows\SoftwareDistribution\DeliveryOptimization"
        # 使用 cleanmgr 组件（如果可用）
        $cmd = Get-Command Start-DedupJob -ErrorAction SilentlyContinue
        return $cleaned
    } catch { return 0 }
}

function Clear-ThumbnailCache {
    $cleaned = 0
    try {
        $thumbPath = "$env:LOCALAPPDATA\Microsoft\Windows\Explorer"
        $items = Get-ChildItem -Path $thumbPath -Filter "thumbcache_*" -Force -ErrorAction SilentlyContinue
        foreach ($item in $items) {
            $cleaned += $item.Length
            Remove-Item $item.FullName -Force -ErrorAction SilentlyContinue
            $Script:CleanedFiles++
        }
    } catch { }
    return $cleaned
}

function Clear-ThumbsDbOnDrive {
    param([string]$Drive = "D:\")
    $cleaned = 0
    if (-not (Test-Path $Drive)) { return 0 }
    try {
        $items = Get-ChildItem -Path $Drive -Filter "Thumbs.db" -Recurse -Force -ErrorAction SilentlyContinue
        foreach ($item in $items) {
            $cleaned += $item.Length
            Remove-Item $item.FullName -Force -ErrorAction SilentlyContinue
            $Script:CleanedFiles++
        }
    } catch { }
    return $cleaned
}

function Clear-DesktopIniOnDrive {
    param([string]$Drive = "D:\")
    $cleaned = 0
    if (-not (Test-Path $Drive)) { return 0 }
    try {
        $items = Get-ChildItem -Path $Drive -Filter "desktop.ini" -Recurse -Force -ErrorAction SilentlyContinue
        foreach ($item in $items) {
            $cleaned += $item.Length
            Remove-Item $item.FullName -Force -ErrorAction SilentlyContinue
            $Script:CleanedFiles++
        }
    } catch { }
    return $cleaned
}

function Clear-OldLogFiles {
    param([string]$Drive = "D:\", [int]$DaysOld = 30)
    $cleaned = 0
    if (-not (Test-Path $Drive)) { return 0 }
    try {
        $cutoff = (Get-Date).AddDays(-$DaysOld)
        $extensions = @("*.log", "*.tmp", "*.bak", "*.old")
        foreach ($ext in $extensions) {
            $items = Get-ChildItem -Path $Drive -Filter $ext -Recurse -Force -ErrorAction SilentlyContinue |
                     Where-Object { -not $_.PSIsContainer -and $_.LastWriteTime -lt $cutoff }
            foreach ($item in $items) {
                $cleaned += $item.Length
                Remove-Item $item.FullName -Force -ErrorAction SilentlyContinue
                $Script:CleanedFiles++
            }
        }
    } catch { }
    return $cleaned
}

function Clear-OldBackups {
    param([string]$Drive = "D:\", [int]$DaysOld = 60)
    $cleaned = 0
    if (-not (Test-Path $Drive)) { return 0 }
    try {
        $cutoff = (Get-Date).AddDays(-$DaysOld)
        $backupDirs = @("Backup", "Backups", "backup", "backups", "备份")
        foreach ($dir in $backupDirs) {
            $path = Join-Path $Drive $dir
            if (Test-Path $path) {
                $items = Get-ChildItem -Path $path -Force -ErrorAction SilentlyContinue |
                         Where-Object { $_.LastWriteTime -lt $cutoff }
                foreach ($item in $items) {
                    if ($item.PSIsContainer) {
                        $cleaned += Get-FolderSize $item.FullName
                    } else {
                        $cleaned += $item.Length
                    }
                    Remove-Item $item.FullName -Recurse -Force -ErrorAction SilentlyContinue
                    $Script:CleanedFiles++
                }
            }
        }
    } catch { }
    return $cleaned
}

function Clear-DiskCleanupManager {
    # 设置 cleanmgr 自动清理参数
    $basePath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\VolumeCaches"
    $cleanupItems = @(
        "Temporary Files", "Temporary Sync Files", "Thumbnail Cache",
        "Temporary Setup Files", "Old ChkDsk Files", "Setup Log Files",
        "System error memory dump files", "System error minidump files",
        "Windows Error Reporting Files", "Windows Upgrade Log Files",
        "Delivery Optimization Files", "Previous Installations"
    )
    
    $cleaned = 0
    foreach ($item in $cleanupItems) {
        $key = "$basePath\$item"
        if (Test-Path $key) {
            try {
                Set-ItemProperty -Path $key -Name "StateFlags0064" -Value 2 -Type DWORD -ErrorAction SilentlyContinue
            } catch {}
        }
    }
    
    # 尝试运行 cleanmgr
    try {
        $process = Start-Process "cleanmgr.exe" -ArgumentList "/sagerun:64" -Wait -PassThru -WindowStyle Hidden -ErrorAction SilentlyContinue
    } catch {}
    
    return $cleaned
}

function Clear-DDriveBrowserCache {
    param([string]$Drive = "D:\")
    $cleaned = 0
    if (-not (Test-Path $Drive)) { return 0 }
    
    # 搜索D盘上可能的浏览器缓存目录
    $browserPatterns = @(
        "Chrome\User Data\Default\Cache",
        "Firefox\Profiles",
        "Edge\User Data\Default\Cache",
        "Opera\*\Cache"
    )
    
    foreach ($pattern in $browserPatterns) {
        $fullPath = Join-Path $Drive $pattern
        $dirs = Get-ChildItem -Path (Split-Path $fullPath) -Directory -Force -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -like (Split-Path $fullPath -Leaf) }
    }
    return $cleaned
}

function Clear-SteamCache {
    param([string]$Drive = "D:\")
    $cleaned = 0
    if (-not (Test-Path $Drive)) { return 0 }
    
    $steamPaths = @(
        "$Drive\Steam\steamapps\downloading",
        "$Drive\Steam\steamapps\temp",
        "$Drive\Program Files (x86)\Steam\steamapps\downloading",
        "$Drive\Program Files (x86)\Steam\steamapps\temp",
        "$Drive\Games\Steam\steamapps\downloading",
        "$Drive\Game\Steam\steamapps\downloading"
    )
    
    foreach ($path in $steamPaths) {
        if (Test-Path $path) {
            $cleaned += Clear-FolderContents $path
        }
    }
    return $cleaned
}

function Clear-PackageManagerCache {
    param([string]$Drive = "D:\")
    $cleaned = 0
    
    $cachePaths = @(
        "$env:LOCALAPPDATA\pip\cache",
        "$env:LOCALAPPDATA\pipenv\cache", 
        "$env:APPDATA\npm-cache",
        "$env:LOCALAPPDATA\Yarn\Cache",
        "$env:LOCALAPPDATA\Microsoft\WindowsApps",
        "$env:USERPROFILE\.nuget\packages",
        "$env:LOCALAPPDATA\NuGet\v3-cache",
        "$env:LOCALAPPDATA\Cargo\cache",
        "$env:USERPROFILE\.gradle\caches"
    )
    
    # 只清理7天以上的缓存
    $cutoff = (Get-Date).AddDays(-7)
    foreach ($path in $cachePaths) {
        if (Test-Path $path) {
            try {
                $items = Get-ChildItem -Path $path -Recurse -Force -ErrorAction SilentlyContinue |
                         Where-Object { -not $_.PSIsContainer -and $_.LastWriteTime -lt $cutoff }
                foreach ($item in $items) {
                    $cleaned += $item.Length
                    Remove-Item $item.FullName -Force -ErrorAction SilentlyContinue
                    $Script:CleanedFiles++
                }
            } catch {}
        }
    }
    return $cleaned
}

function Clear-WinSxSBackup {
    # 清理 WinSxS 中旧版本组件（安全方式）
    try {
        $process = Start-Process "DISM.exe" -ArgumentList "/Online", "/Cleanup-Image", "/StartComponentCleanup" -Wait -PassThru -WindowStyle Hidden -ErrorAction SilentlyContinue
        return 0 # 无法精确测量
    } catch { return 0 }
}

# ─── 扫描函数 ────────────────────────────────────────────

function Show-ScanResults {
    Clear-Host
    Write-Colored "╔══════════════════════════════════════════════════════╗" "Cyan"
    Write-Colored "║           🔍  正在扫描可清理的文件...               ║" "Cyan"
    Write-Colored "╚══════════════════════════════════════════════════════╝" "Cyan"
    Write-Host ""
    
    $results = @()
    $totalSize = 0
    
    # C盘扫描
    Write-Colored "  📂 [C盘] 扫描中..." "Yellow"
    
    $cPaths = @(
        @{ Name="系统临时文件";        Path="$env:TEMP" },
        @{ Name="Windows临时文件";     Path="C:\Windows\Temp" },
        @{ Name="Windows更新缓存";     Path="C:\Windows\SoftwareDistribution\Download" },
        @{ Name="预取文件";            Path="C:\Windows\Prefetch" },
        @{ Name="缩略图缓存";          Path="$env:LOCALAPPDATA\Microsoft\Windows\Explorer" },
        @{ Name="Windows错误报告";     Path="C:\ProgramData\Microsoft\Windows\WER" },
        @{ Name="DirectX着色器缓存";   Path="$env:LOCALAPPDATA\D3DSCache" },
        @{ Name="临时互联网文件";      Path="$env:LOCALAPPDATA\Microsoft\Windows\INetCache" },
        @{ Name="崩溃转储文件";        Path="$env:LOCALAPPDATA\CrashDumps" },
        @{ Name="系统日志文件";        Path="C:\Windows\Logs" },
        @{ Name="CBS日志";             Path="C:\Windows\Logs\CBS" },
        @{ Name="Delivery优化文件";    Path="C:\Windows\SoftwareDistribution\DeliveryOptimization" },
        @{ Name="NVIDIA着色器缓存";    Path="$env:LOCALAPPDATA\NVIDIA\DXCache" },
        @{ Name="NVIDIA GLCache";      Path="$env:LOCALAPPDATA\NVIDIA\GLCache" },
    )
    
    foreach ($item in $cPaths) {
        $size = Get-FolderSize $item.Path
        if ($size -gt 0) {
            $results += @{ Name=$item.Name; Path=$item.Path; Size=$size; Drive="C" }
            $totalSize += $size
            Write-Colored "    ✓ $($item.Name): $(Get-SizeString $size)" "Gray"
        }
    }
    
    # D盘扫描
    Write-Host ""
    Write-Colored "  📂 [D盘] 扫描中..." "Yellow"
    
    if (Test-Path "D:\") {
        # D:\Temp
        if (Test-Path "D:\Temp") {
            $size = Get-FolderSize "D:\Temp"
            if ($size -gt 0) {
                $results += @{ Name="[D盘]临时文件"; Path="D:\Temp"; Size=$size; Drive="D" }
                $totalSize += $size
                Write-Colored "    ✓ [D盘]临时文件: $(Get-SizeString $size)" "Gray"
            }
        }
        
        # D盘回收站
        if (Test-Path "D:\`$Recycle.Bin") {
            $size = Get-FolderSize "D:\`$Recycle.Bin"
            if ($size -gt 0) {
                $results += @{ Name="[D盘]回收站"; Path="D:\`$Recycle.Bin"; Size=$size; Drive="D" }
                $totalSize += $size
                Write-Colored "    ✓ [D盘]回收站: $(Get-SizeString $size)" "Gray"
            }
        }
        
        # Thumbs.db 文件
        Write-Colored "    ...扫描 Thumbs.db 文件" "DarkGray"
        $thumbs = Get-ChildItem -Path "D:\" -Filter "Thumbs.db" -Recurse -Force -ErrorAction SilentlyContinue
        $thumbSize = ($thumbs | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum ?? 0
        if ($thumbSize -gt 0) {
            $results += @{ Name="[D盘]Thumbs.db文件"; Path="D:\Thumbs.db"; Size=$thumbSize; Drive="D" }
            $totalSize += $thumbSize
            Write-Colored "    ✓ [D盘]Thumbs.db文件: $(Get-SizeString $thumbSize) ($($thumbs.Count) 个)" "Gray"
        }
        
        # Desktop.ini 文件
        $desktopInis = Get-ChildItem -Path "D:\" -Filter "desktop.ini" -Recurse -Force -ErrorAction SilentlyContinue
        $iniSize = ($desktopInis | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum ?? 0
        if ($iniSize -gt 0) {
            $results += @{ Name="[D盘]Desktop.ini文件"; Path="D:\desktop.ini"; Size=$iniSize; Drive="D" }
            $totalSize += $iniSize
            Write-Colored "    ✓ [D盘]Desktop.ini文件: $(Get-SizeString $iniSize) ($($desktopInis.Count) 个)" "Gray"
        }
        
        # 旧日志和备份
        $logDirs = @("Log", "Logs", "log", "logs")
        foreach ($dir in $logDirs) {
            $path = "D:\$dir"
            if (Test-Path $path) {
                $size = Get-FolderSize $path
                if ($size -gt 0) {
                    $results += @{ Name="[D盘]日志文件-$dir"; Path=$path; Size=$size; Drive="D" }
                    $totalSize += $size
                    Write-Colored "    ✓ [D盘]日志文件 ($dir): $(Get-SizeString $size)" "Gray"
                }
            }
        }
        
        # Steam下载缓存
        $steamPaths = @(
            "D:\Steam\steamapps\downloading",
            "D:\Program Files (x86)\Steam\steamapps\downloading",
            "D:\Games\Steam\steamapps\downloading"
        )
        foreach ($sp in $steamPaths) {
            if (Test-Path $sp) {
                $size = Get-FolderSize $sp
                if ($size -gt 0) {
                    $results += @{ Name="[D盘]Steam下载缓存"; Path=$sp; Size=$size; Drive="D" }
                    $totalSize += $size
                    Write-Colored "    ✓ [D盘]Steam下载缓存: $(Get-SizeString $size)" "Gray"
                }
            }
        }
        
        # 缓存目录
        $cacheDirs = @("Cache", "cache", "缓存")
        foreach ($dir in $cacheDirs) {
            $path = "D:\$dir"
            if (Test-Path $path) {
                $size = Get-FolderSize $path
                if ($size -gt 0) {
                    $results += @{ Name="[D盘]缓存文件-$dir"; Path=$path; Size=$size; Drive="D" }
                    $totalSize += $size
                    Write-Colored "    ✓ [D盘]缓存文件 ($dir): $(Get-SizeString $size)" "Gray"
                }
            }
        }
        
        # 30天以上的 .log/.tmp/.bak 文件
        Write-Colored "    ...扫描旧临时文件" "DarkGray"
        $cutoff = (Get-Date).AddDays(-30)
        $oldTempFiles = @()
        foreach ($ext in @("*.log", "*.tmp", "*.bak")) {
            $oldTempFiles += Get-ChildItem -Path "D:\" -Filter $ext -Recurse -Force -ErrorAction SilentlyContinue |
                            Where-Object { -not $_.PSIsContainer -and $_.LastWriteTime -lt $cutoff }
        }
        $oldSize = ($oldTempFiles | Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum ?? 0
        if ($oldSize -gt 0) {
            $results += @{ Name="[D盘]旧临时文件(30天+)"; Path="D:\*.log/tmp/bak"; Size=$oldSize; Drive="D" }
            $totalSize += $oldSize
            Write-Colored "    ✓ [D盘]旧临时文件: $(Get-SizeString $oldSize) ($($oldTempFiles.Count) 个)" "Gray"
        }
        
    } else {
        Write-Colored "    ⚠ D盘不存在或不可访问" "Red"
    }
    
    Write-Host ""
    
    # 磁盘空间
    $cFree = Get-DriveFreeSpace "C"
    $cTotal = (Get-PSDrive C).Used + (Get-PSDrive C).Free
    $cUsed = $cTotal - $cFree
    
    Write-Colored "  💾 磁盘空间:" "White"
    Write-Colored "    C盘: 已用 $(Get-SizeString $cUsed) / 总共 $(Get-SizeString $cTotal) / 剩余 $(Get-SizeString $cFree)" "Gray"
    
    if (Test-Path "D:\") {
        try {
            $dFree = Get-DriveFreeSpace "D"
            $dTotal = (Get-PSDrive D).Used + (Get-PSDrive D).Free
            $dUsed = $dTotal - $dFree
            Write-Colored "    D盘: 已用 $(Get-SizeString $dUsed) / 总共 $(Get-SizeString $dTotal) / 剩余 $(Get-SizeString $dFree)" "Gray"
        } catch {}
    }
    
    Write-Host ""
    Write-Colored "  🗑️  可清理: $(Get-SizeString $totalSize) 共 $($results.Count) 项" "Green"
    Write-Host ""
    
    return @{ Results = $results; TotalSize = $totalSize }
}

# ─── 执行清理 ────────────────────────────────────────────

function Start-Cleanup {
    param([array]$Items)
    
    $cleaned = 0
    $Script:CleanedFiles = 0
    $step = 0
    $total = $Items.Count
    
    foreach ($item in $Items) {
        $step++
        $pct = [math]::Round(($step / $total) * 100)
        Write-Progress -Activity "正在清理..." -Status "$($item.Name)" -PercentComplete $pct
        
        $before = Get-FolderSize $item.Path
        
        switch -Wildcard ($item.Path) {
            "D:\Thumbs.db" {
                $cleaned += Clear-ThumbsDbOnDrive "D:\"
            }
            "D:\desktop.ini" {
                $cleaned += Clear-DesktopIniOnDrive "D:\"
            }
            "D:\*.log/tmp/bak" {
                $cleaned += Clear-OldLogFiles "D:\" 30
            }
            default {
                $cleaned += Clear-FolderContents $item.Path
            }
        }
    }
    
    Write-Progress -Activity "清理完成" -Completed
    return $cleaned
}

# ─── D盘深度清理 ─────────────────────────────────────────

function Start-DDriveDeepClean {
    Clear-Host
    Write-Colored "╔══════════════════════════════════════════════════════╗" "Magenta"
    Write-Colored "║           🔬  D盘深度清理分析                       ║" "Magenta"
    Write-Colored "╚══════════════════════════════════════════════════════╝" "Magenta"
    Write-Host ""
    
    if (-not (Test-Path "D:\")) {
        Write-Colored "  ⚠ D盘不存在！" "Red"
        Read-Host "  按回车返回"
        return
    }
    
    Write-Colored "  📊 分析D盘大文件和重复文件..." "Yellow"
    Write-Host ""
    
    # 分析大文件 (>100MB)
    Write-Colored "  📦 D盘大文件 (>100MB)，按大小排序（前30个）:" "White"
    Write-Host ""
    
    $largeFiles = Get-ChildItem -Path "D:\" -Recurse -Force -ErrorAction SilentlyContinue |
                  Where-Object { -not $_.PSIsContainer -and $_.Length -gt 100MB } |
                  Sort-Object Length -Descending |
                  Select-Object -First 30
    
    if ($largeFiles) {
        foreach ($file in $largeFiles) {
            $relPath = $file.FullName -replace "D:\\", ""
            if ($relPath.Length -gt 50) { $relPath = "..." + $relPath.Substring($relPath.Length - 47) }
            Write-Colored "    $(Get-SizeString $file.Length)  $relPath" "Gray"
        }
        
        $totalLarge = ($largeFiles | Measure-Object -Property Length -Sum).Sum
        Write-Host ""
        Write-Colored "  大文件总计: $(Get-SizeString $totalLarge)" "Yellow"
    } else {
        Write-Colored "    未找到 >100MB 的文件" "Gray"
    }
    
    Write-Host ""
    
    # 分析空目录
    Write-Colored "  📁 D盘空目录:" "White"
    $emptyDirs = Get-ChildItem -Path "D:\" -Directory -Recurse -Force -ErrorAction SilentlyContinue |
                 Where-Object { (Get-ChildItem $_.FullName -Force -ErrorAction SilentlyContinue).Count -eq 0 } |
                 Select-Object -First 20
    $emptyCount = ($emptyDirs | Measure-Object).Count
    if ($emptyCount -gt 0) {
        foreach ($dir in $emptyDirs) {
            $relPath = $dir.FullName -replace "D:\\", ""
            if ($relPath.Length -gt 55) { $relPath = "..." + $relPath.Substring($relPath.Length - 52) }
            Write-Colored "    📂 $relPath" "Gray"
        }
        Write-Colored "    ...共 $emptyCount 个空目录（显示前20个）" "DarkGray"
    } else {
        Write-Colored "    未找到空目录" "Gray"
    }
    
    Write-Host ""
    Write-Colored "  提示: 建议手动检查大文件列表，确认后可以删除" "Yellow"
    Read-Host "  按回车返回主菜单"
}

# ─── 系统优化 ────────────────────────────────────────────

function Start-SystemOptimization {
    Clear-Host
    Write-Colored "╔══════════════════════════════════════════════════════╗" "Blue"
    Write-Colored "║           ⚙️  系统优化                               ║" "Blue"
    Write-Colored "╚══════════════════════════════════════════════════════╝" "Blue"
    Write-Host ""
    
    $options = @(
        "清理系统组件 (WinSxS)",
        "运行磁盘碎片整理",
        "清理DNS缓存",
        "清理字体缓存",
        "运行 SFC /scannow",
        "返回主菜单"
    )
    
    for ($i = 0; $i -lt $options.Count; $i++) {
        Write-Colored "  [$($i+1)] $($options[$i])" "White"
    }
    Write-Host ""
    $choice = Read-Host "  请选择 (1-$($options.Count))"
    
    switch ($choice) {
        "1" {
            Write-Colored "`n  🔧 清理WinSxS旧组件..." "Yellow"
            Write-Colored "  (这可能需要几分钟)" "Gray"
            $process = Start-Process "DISM.exe" -ArgumentList "/Online", "/Cleanup-Image", "/StartComponentCleanup" -Wait -PassThru -NoNewWindow
            if ($process.ExitCode -eq 0) {
                Write-Colored "  ✅ WinSxS清理完成" "Green"
            } else {
                Write-Colored "  ⚠ WinSxS清理可能未完成 (Exit: $($process.ExitCode))" "Yellow"
            }
        }
        "2" {
            Write-Colored "`n  🔧 分析磁盘碎片..." "Yellow"
            $process = Start-Process "defrag.exe" -ArgumentList "C: /A" -Wait -PassThru -NoNewWindow
            $answer = Read-Host "  是否执行碎片整理? (y/n)"
            if ($answer -eq 'y') {
                Start-Process "defrag.exe" -ArgumentList "C: /O" -Wait -NoNewWindow
                Write-Colored "  ✅ 碎片整理完成" "Green"
            }
        }
        "3" {
            Write-Colored "`n  🔧 清理DNS缓存..." "Yellow"
            $result = ipconfig /flushdns 2>&1
            Write-Colored "  ✅ DNS缓存已清理" "Green"
        }
        "4" {
            Write-Colored "`n  🔧 清理字体缓存..." "Yellow"
            try {
                Stop-Service -Name FontCache -Force -ErrorAction SilentlyContinue
                Remove-Item "$env:LOCALAPPDATA\FontCache\*" -Force -ErrorAction SilentlyContinue
                Remove-Item "C:\Windows\System32\FNTCACHE.DAT" -Force -ErrorAction SilentlyContinue
                Start-Service -Name FontCache -ErrorAction SilentlyContinue
                Write-Colored "  ✅ 字体缓存已清理" "Green"
            } catch {
                Write-Colored "  ⚠ 部分字体缓存无法清理" "Yellow"
            }
        }
        "5" {
            Write-Colored "`n  🔧 运行系统文件检查 (可能需要10-30分钟)..." "Yellow"
            $answer = Read-Host "  确认运行? (y/n)"
            if ($answer -eq 'y') {
                Start-Process "sfc.exe" -ArgumentList "/scannow" -Wait -NoNewWindow
                Write-Colored "  ✅ 系统文件检查完成" "Green"
            }
        }
        "6" { return }
    }
    
    Read-Host "`n  按回车返回"
}

# ─── 主界面 ──────────────────────────────────────────────

function Show-MainMenu {
    Clear-Host
    
    # 检查管理员权限
    $isAdmin = Test-IsAdmin
    $adminStatus = if ($isAdmin) { "✅ 已获取" } else { "⚠️  未获取(部分功能受限)" }
    $adminColor = if ($isAdmin) { "Green" } else { "Yellow" }
    
    # 磁盘空间
    $cFree = Get-DriveFreeSpace "C"
    $dFree = if (Test-Path "D:\") { Get-DriveFreeSpace "D" } else { -1 }
    
    Write-Colored "╔══════════════════════════════════════════════════════════╗" "Cyan"
    Write-Colored "║         🧹  Windows 11 垃圾清理工具  v2.0              ║" "Cyan"
    Write-Colored "╠══════════════════════════════════════════════════════════╣" "Cyan"
    Write-Colored "║  管理员权限: $adminStatus" $adminColor
    Write-Colored "║  C盘剩余: $(Get-SizeString $cFree)" "White"
    if ($dFree -ge 0) {
        Write-Colored "║  D盘剩余: $(Get-SizeString $dFree)" "White"
    } else {
        Write-Colored "║  D盘: 不可用" "DarkGray"
    }
    Write-Colored "╚══════════════════════════════════════════════════════════╝" "Cyan"
    Write-Host ""
    Write-Colored "  [1] 🔍 扫描可清理文件" "White"
    Write-Colored "  [2] 🧹 一键智能清理 (推荐)" "Green"
    Write-Colored "  [3] 📂 自定义选择清理" "White"
    Write-Colored "  [4] 🔬 D盘深度分析" "Magenta"
    Write-Colored "  [5] ⚙️  系统优化" "Blue"
    Write-Colored "  [6] 🚪 退出" "Gray"
    Write-Host ""
    
    return Read-Host "  请选择 (1-6)"
}

# ─── 主循环 ──────────────────────────────────────────────

do {
    $choice = Show-MainMenu
    
    switch ($choice) {
        "1" {
            # 扫描
            $scanResult = Show-ScanResults
            Read-Host "  按回车返回主菜单"
        }
        "2" {
            # 一键清理
            $scanResult = Show-ScanResults
            if ($scanResult.TotalSize -gt 0) {
                Write-Colored "`n  ⚡ 开始清理..." "Yellow"
                $cleaned = Start-Cleanup $scanResult.Results
                
                Write-Host ""
                Write-Colored "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" "Green"
                Write-Colored "  ✅ 清理完成！" "Green"
                Write-Colored "  📊 清理文件数: $($Script:CleanedFiles) 个" "White"
                Write-Colored "  💾 释放空间: $(Get-SizeString $cleaned)" "White"
                Write-Colored "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" "Green"
            } else {
                Write-Colored "`n  ✨ 系统很干净，无需清理！" "Green"
            }
            Read-Host "`n  按回车返回主菜单"
        }
        "3" {
            # 自定义清理
            $scanResult = Show-ScanResults
            if ($scanResult.Results.Count -gt 0) {
                Write-Colored "  选择要清理的项目（输入编号，逗号分隔，或输入 all 全选）:" "Yellow"
                $input = Read-Host "  "
                
                if ($input -eq 'all') {
                    $selected = $scanResult.Results
                } else {
                    $indices = $input -split ',' | ForEach-Object { [int]$_.Trim() - 1 }
                    $selected = $indices | Where-Object { $_ -ge 0 -and $_ -lt $scanResult.Results.Count } |
                                ForEach-Object { $scanResult.Results[$_] }
                }
                
                if ($selected.Count -gt 0) {
                    Write-Colored "`n  ⚡ 开始清理选定的 $($selected.Count) 项..." "Yellow"
                    $cleaned = Start-Cleanup $selected
                    Write-Colored "`n  ✅ 完成！释放 $(Get-SizeString $cleaned)" "Green"
                } else {
                    Write-Colored "  ⚠ 未选择任何项目" "Yellow"
                }
            }
            Read-Host "`n  按回车返回主菜单"
        }
        "4" {
            # D盘深度分析
            Start-DDriveDeepClean
        }
        "5" {
            # 系统优化
            Start-SystemOptimization
        }
        "6" {
            Write-Colored "`n  👋 再见！" "Cyan"
            Start-Sleep -Seconds 1
            break
        }
        default {
            Write-Colored "  ⚠ 无效选择" "Red"
            Start-Sleep -Seconds 1
        }
    }
} while ($choice -ne "6")
