# 🧹 Windows 11 垃圾清理工具 v2.0

单文件独立版，C盘 + D盘 全面清理。

## 🚀 快速开始

### 方式一：直接使用（推荐）

> 已在 Windows 上打包好，直接双击运行

### 方式二：自己打包 EXE

1. 安装 Python 3.8+（[下载地址](https://www.python.org/downloads/)），安装时勾选 **Add Python to PATH**
2. 双击 `build_windows.bat`，等 1-3 分钟
3. 编译好的 EXE 在 `dist\Win11Cleanup.exe`

### 方式三：Python 直接运行

```
python win11_cleanup.py
```

## 📋 清理范围

### C盘（系统盘）

| 项目 | 路径 |
|------|------|
| 系统临时文件 | `%TEMP%` |
| Windows 临时文件 | `C:\Windows\Temp` |
| Windows 更新缓存 | `SoftwareDistribution\Download` |
| 预取文件 | `C:\Windows\Prefetch` |
| 缩略图缓存 | `Explorer\thumbcache_*` |
| DirectX 着色器缓存 | `D3DSCache` |
| NVIDIA 着色器缓存 | `NVIDIA\DXCache` / `GLCache` |
| Windows 错误报告 | `WER` |
| 崩溃转储文件 | `CrashDumps` |
| 系统日志 | `C:\Windows\Logs` |
| Delivery 优化文件 | `DeliveryOptimization` |
| 临时互联网文件 | `INetCache` |

### D盘（数据盘）

| 项目 | 说明 |
|------|------|
| D:\Temp 临时文件 | 直接清理 |
| D:\$Recycle.Bin | 回收站残留 |
| Thumbs.db 文件 | 全盘递归搜索删除 |
| Desktop.ini 文件 | 全盘递归搜索删除 |
| 旧日志文件 | 30 天以上 `.log` / `.tmp` / `.bak` |
| 旧备份文件 | Backup/Backups 目录中 60 天以上 |
| Steam 下载缓存 | 自动检测常见 Steam 路径 |
| 包管理器缓存 | pip / yarn / nuget / cargo |

### 附加功能

- 🔍 **扫描模式** — 先看能清多少，再决定
- ⚡ **一键清理** — 扫描 + 自动清理全部
- 📂 **自定义清理** — 手动选择项目
- 🔬 **D盘深度分析** — 大文件排名、空目录检测、重复文件
- ⚙️ **系统优化** — DNS 清理、字体缓存、WinSxS、磁盘碎片

## ⚠️ 注意事项

- 建议**右键 → 以管理员身份运行**（不提权也能用，部分项会跳过）
- Steam 用户：确保没有正在下载的游戏
- 首次建议先用 [1] 扫描看看结果，再决定清理
- 跳过被占用的文件，不会导致系统崩溃

## 📁 文件说明

```
win11-cleanup/
├── win11_cleanup.py    # 主程序（Python 源码）
├── Win11Cleanup.ps1    # PowerShell 版（备用）
├── build_windows.bat   # Windows 一键打包脚本
├── test_cleanup.py     # 测试套件
├── 启动清理工具.bat     # PowerShell 版启动器
└── README.md
```

## 🧪 测试结果

```
✅ size_str          - 单位转换正常
✅ folder_size       - 目录大小计算 11264 bytes
✅ CleanupEngine     - 清理 13 个文件，释放 42.99 KB
✅ clean_old_files   - 精确清理 30 天以上文件
✅ clean_pattern     - 通配符过滤正常
✅ scan_c_drive      - C盘扫描正常
✅ scan_d_drive      - D盘扫描 8 项，清理释放 14.74 MB

总测试: 7 通过 / 0 失败
一键清理实测: 3471 个文件，释放 38.74 MB
```
