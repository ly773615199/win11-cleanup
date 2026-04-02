# 🧹 Windows 11 垃圾清理工具 v2.1

单文件独立版，C盘 + D盘 全面清理。安全清理，日志可溯。

## 🆕 v2.1 更新

- 🔒 **安全路径白名单** — 自动拦截危险路径，防止误删系统文件
- 🌐 **浏览器缓存清理** — Chrome / Edge / Firefox 缓存一键清除
- 📋 **操作日志** — 所有删除操作记录到 `cleanup.log`，可追溯
- 🔍 **哈希精确去重** — D盘深度分析改用 MD5 哈希比对，消除误报
- 🛡️ **具体异常捕获** — 替换 bare `except`，错误信息不再被吞掉
- 📝 **类型注解** — 全函数 type hints，IDE 友好
- ⚙️ **CI 自动测试** — GitHub Actions 多版本 Python 测试

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

### 🌐 浏览器缓存（新增）

| 项目 | 说明 |
|------|------|
| Chrome 缓存 | Cache_Data + ServiceWorker |
| Edge 缓存 | Cache_Data + ServiceWorker |
| Firefox 缓存 | cache2 + startupCache |

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
- 🔬 **D盘深度分析** — 大文件排名、空目录检测、MD5 哈希重复文件检测
- ⚙️ **系统优化** — DNS 清理、字体缓存、WinSxS、磁盘碎片
- 📋 **清理日志** — 所有操作记录可查

## 🔒 安全特性

- **路径白名单** — 只清理已知安全的临时/缓存路径
- **黑名单拦截** — System32、Program Files、pagefile.sys 等绝不触碰
- **操作日志** — 每次清理记录到 `cleanup.log`，可审计
- **跳过占用文件** — 被占用的文件自动跳过，不会导致系统崩溃

## ⚠️ 注意事项

- 建议**右键 → 以管理员身份运行**（不提权也能用，部分项会跳过）
- Steam 用户：确保没有正在下载的游戏
- 首次建议先用 [1] 扫描看看结果，再决定清理
- 清理浏览器缓存会退出浏览器，建议先保存工作

## 📁 文件说明

```
win11-cleanup/
├── win11_cleanup.py        # 主程序（Python 源码）
├── Win11Cleanup.ps1        # PowerShell 版（备用）
├── build_windows.bat       # Windows 一键打包脚本
├── test_cleanup.py         # 测试套件（11 项）
├── 启动清理工具.bat         # PowerShell 版启动器
├── LICENSE                 # MIT 许可证
├── .gitignore              # Git 忽略规则
├── cleanup.log             # 运行时生成的操作日志
└── .github/workflows/
    └── test.yml            # CI 自动测试
```

## 🧪 测试

```bash
python test_cleanup.py
```

## 📄 许可证

[MIT](LICENSE)
