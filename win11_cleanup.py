#!/usr/bin/env python3
"""
Windows 11 垃圾清理工具 v2.0 - 独立可执行版
支持 C盘 + D盘 全面清理
"""

import os
import sys
import shutil
import ctypes
import subprocess
import time
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── 跨平台检测 ─────────────────────────────────────────
IS_WINDOWS = sys.platform == "win32"

# ─── 颜色 ────────────────────────────────────────────────
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"
    WHITE = "\033[97m"

def colored(text, color):
    return f"{color}{text}{Colors.RESET}"

def print_colored(text, color=Colors.WHITE):
    print(colored(text, color))

def banner():
    print()
    print_colored("╔══════════════════════════════════════════════════════════╗", Colors.CYAN)
    print_colored("║         🧹  Windows 11 垃圾清理工具  v2.0              ║", Colors.CYAN)
    print_colored("║            单文件独立版 — 无需安装依赖                  ║", Colors.CYAN)
    print_colored("╚══════════════════════════════════════════════════════════╝", Colors.CYAN)

# ─── 工具函数 ────────────────────────────────────────────

def size_str(n):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"

def folder_size(path):
    """计算目录大小（bytes），跳过无法访问的文件"""
    total = 0
    try:
        p = Path(path)
        if not p.exists():
            return 0
        if p.is_file():
            return p.stat().st_size
        for f in p.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass
    return total

def drive_free_space(drive):
    """获取磁盘剩余空间"""
    if not IS_WINDOWS:
        stat = shutil.disk_usage("/") if drive == "C" else None
        if drive == "D":
            try:
                stat = shutil.disk_usage("/tmp")  # 模拟
            except:
                return -1
        return stat.free if stat else -1
    
    try:
        _, _, free = shutil.disk_usage(f"{drive}:\\")
        return free
    except:
        return -1

def is_admin():
    """检查管理员权限"""
    if not IS_WINDOWS:
        return os.geteuid() == 0
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False

def get_temp_dir():
    if IS_WINDOWS:
        return os.environ.get("TEMP", os.environ.get("TMP", r"C:\Windows\Temp"))
    return tempfile.gettempdir()

def get_local_appdata():
    if IS_WINDOWS:
        return os.environ.get("LOCALAPPDATA", "")
    return os.path.expanduser("~/.local/share")

def get_appdata():
    if IS_WINDOWS:
        return os.environ.get("APPDATA", "")
    return os.path.expanduser("~/.config")

# ─── 核心清理引擎 ────────────────────────────────────────

class CleanupEngine:
    def __init__(self):
        self.total_cleaned = 0
        self.total_files = 0
        self.errors = 0
        self.results = []  # {name, path, size, drive, status}
    
    def clean_folder(self, path, filter_ext=None):
        """清理目录内容，返回清理的字节数"""
        cleaned = 0
        p = Path(path)
        if not p.exists():
            return 0
        
        try:
            for item in p.rglob("*"):
                try:
                    if filter_ext and item.is_file() and item.suffix.lower() not in filter_ext:
                        continue
                    if item.is_file():
                        size = item.stat().st_size
                        item.unlink(missing_ok=True)
                        cleaned += size
                        self.total_files += 1
                    elif item.is_dir():
                        try:
                            item.rmdir()  # 只删空目录
                        except:
                            pass
                except (PermissionError, OSError):
                    self.errors += 1
                    continue
            
            # 再次尝试清理空目录
            for item in sorted(p.rglob("*"), key=lambda x: len(str(x)), reverse=True):
                if item.is_dir():
                    try:
                        item.rmdir()
                    except:
                        pass
        except (PermissionError, OSError):
            self.errors += 1
        
        return cleaned
    
    def clean_pattern(self, base_path, pattern):
        """清理匹配模式的文件"""
        cleaned = 0
        p = Path(base_path)
        if not p.exists():
            return 0
        
        try:
            for item in p.rglob(pattern):
                try:
                    if item.is_file():
                        size = item.stat().st_size
                        item.unlink(missing_ok=True)
                        cleaned += size
                        self.total_files += 1
                except (PermissionError, OSError):
                    self.errors += 1
                    continue
        except (PermissionError, OSError):
            pass
        
        return cleaned
    
    def clean_old_files(self, base_path, patterns, days=30):
        """清理指定天数以上的文件"""
        cleaned = 0
        p = Path(base_path)
        if not p.exists():
            return 0
        
        cutoff = datetime.now() - timedelta(days=days)
        
        for pattern in patterns:
            try:
                for item in p.rglob(pattern):
                    try:
                        if item.is_file():
                            mtime = datetime.fromtimestamp(item.stat().st_mtime)
                            if mtime < cutoff:
                                size = item.stat().st_size
                                item.unlink(missing_ok=True)
                                cleaned += size
                                self.total_files += 1
                    except (PermissionError, OSError):
                        self.errors += 1
                        continue
            except (PermissionError, OSError):
                pass
        
        return cleaned
    
    def add_result(self, name, path, size, drive, status="found"):
        self.results.append({
            "name": name, "path": path, "size": size,
            "drive": drive, "status": status
        })

# ─── C盘清理项 ──────────────────────────────────────────

def scan_c_drive(engine):
    """扫描C盘可清理项"""
    local_appdata = get_local_appdata()
    appdata = get_appdata()
    temp_dir = get_temp_dir()
    
    c_items = []
    
    if IS_WINDOWS:
        c_items = [
            ("系统临时文件", temp_dir),
            ("Windows临时文件", r"C:\Windows\Temp"),
            ("Windows更新缓存", r"C:\Windows\SoftwareDistribution\Download"),
            ("预取文件", r"C:\Windows\Prefetch"),
            ("缩略图缓存", os.path.join(local_appdata, r"Microsoft\Windows\Explorer")),
            ("Windows错误报告", r"C:\ProgramData\Microsoft\Windows\WER"),
            ("DirectX着色器缓存", os.path.join(local_appdata, "D3DSCache")),
            ("临时互联网文件", os.path.join(local_appdata, r"Microsoft\Windows\INetCache")),
            ("崩溃转储文件", os.path.join(local_appdata, "CrashDumps")),
            ("最近文件记录", os.path.join(appdata, r"Microsoft\Windows\Recent")),
            ("系统日志文件", r"C:\Windows\Logs"),
            ("CBS日志", r"C:\Windows\Logs\CBS"),
            ("Delivery优化文件", r"C:\Windows\SoftwareDistribution\DeliveryOptimization"),
            ("NVIDIA DX着色器", os.path.join(local_appdata, r"NVIDIA\DXCache")),
            ("NVIDIA GL缓存", os.path.join(local_appdata, r"NVIDIA\GLCache")),
            ("DirectX ShaderCache 2", os.path.join(local_appdata, r"Microsoft\DirectX Shader Cache")),
        ]
    else:
        # Linux 测试模式 - 使用模拟路径
        home = os.path.expanduser("~")
        c_items = [
            ("[测试] /tmp 内容", "/tmp"),
            ("[测试] ~/.cache", os.path.join(home, ".cache")),
        ]
    
    print()
    print_colored("  📂 [C盘] 扫描中...", Colors.YELLOW)
    
    for name, path in c_items:
        if not path:
            continue
        size = folder_size(path)
        if size > 0:
            engine.add_result(name, path, size, "C")
            print_colored(f"    ✓ {name}: {size_str(size)}", Colors.GRAY)

def clean_c_drive(engine, items):
    """执行C盘清理"""
    for item in items:
        name = item["name"]
        path = item["path"]
        
        print_colored(f"    🧹 {name}...", Colors.YELLOW)
        
        if name in ("Windows更新缓存", "Delivery优化文件"):
            # 尝试停止服务后再清理
            if IS_WINDOWS:
                try:
                    subprocess.run(["net", "stop", "wuauserv"], capture_output=True, timeout=10)
                    time.sleep(0.5)
                except:
                    pass
            
            cleaned = engine.clean_folder(path)
            
            if IS_WINDOWS:
                try:
                    subprocess.run(["net", "start", "wuauserv"], capture_output=True, timeout=10)
                except:
                    pass
        elif "缩略图" in name:
            # 只清理 thumbcache_* 文件
            cleaned = engine.clean_pattern(path, "thumbcache_*")
        elif "NVIDIA" in name or "着色器" in name:
            cleaned = engine.clean_folder(path)
        else:
            cleaned = engine.clean_folder(path)
        
        engine.total_cleaned += cleaned
        item["status"] = "done"
        item["cleaned"] = cleaned

# ─── D盘清理项 ──────────────────────────────────────────

def scan_d_drive(engine):
    """扫描D盘可清理项"""
    if IS_WINDOWS:
        d_root = "D:\\"
    else:
        # Linux 测试模式 - 使用测试目录
        d_root = "/tmp/d_drive_test/"
        os.makedirs(d_root, exist_ok=True)
        # 创建一些测试文件
        test_dirs = ["Temp", "Logs", "Cache", "Backup"]
        for td in test_dirs:
            tp = os.path.join(d_root, td)
            os.makedirs(tp, exist_ok=True)
            for i in range(3):
                with open(os.path.join(tp, f"test_{i}.tmp"), "w") as f:
                    f.write("x" * 1024 * (i + 1) * 100)
        # 创建一些旧文件
        old_file = os.path.join(d_root, "old_log.log")
        with open(old_file, "w") as f:
            f.write("old log content" * 1000)
        os.utime(old_file, (time.time() - 40*86400, time.time() - 40*86400))
        
        for name in ["Thumbs.db", "desktop.ini"]:
            for subdir in ["a", "b", "c"]:
                p = os.path.join(d_root, subdir)
                os.makedirs(p, exist_ok=True)
                with open(os.path.join(p, name), "w") as f:
                    f.write("cache")
    
    if not os.path.exists(d_root):
        print_colored("    ⚠ D盘不存在", Colors.RED)
        return
    
    print()
    print_colored("  📂 [D盘] 扫描中...", Colors.YELLOW)
    
    # D:\Temp
    temp_path = os.path.join(d_root, "Temp")
    if os.path.exists(temp_path):
        size = folder_size(temp_path)
        if size > 0:
            engine.add_result("[D盘]临时文件", temp_path, size, "D")
            print_colored(f"    ✓ [D盘]临时文件: {size_str(size)}", Colors.GRAY)
    
    # D:\$Recycle.Bin
    recycle_path = os.path.join(d_root, "$Recycle.Bin")
    if os.path.exists(recycle_path):
        size = folder_size(recycle_path)
        if size > 0:
            engine.add_result("[D盘]回收站", recycle_path, size, "D")
            print_colored(f"    ✓ [D盘]回收站: {size_str(size)}", Colors.GRAY)
    
    # Thumbs.db
    print_colored("    ...扫描 Thumbs.db", Colors.DARKGRAY if hasattr(Colors, 'DARKGRAY') else Colors.GRAY)
    thumbs_size = 0
    thumbs_count = 0
    try:
        for f in Path(d_root).rglob("Thumbs.db"):
            try:
                thumbs_size += f.stat().st_size
                thumbs_count += 1
            except:
                pass
    except:
        pass
    if thumbs_size > 0:
        engine.add_result("[D盘]Thumbs.db文件", d_root, thumbs_size, "D")
        print_colored(f"    ✓ [D盘]Thumbs.db: {size_str(thumbs_size)} ({thumbs_count} 个)", Colors.GRAY)
    
    # Desktop.ini
    ini_size = 0
    ini_count = 0
    try:
        for f in Path(d_root).rglob("desktop.ini"):
            try:
                ini_size += f.stat().st_size
                ini_count += 1
            except:
                pass
    except:
        pass
    if ini_size > 0:
        engine.add_result("[D盘]Desktop.ini文件", d_root, ini_size, "D")
        print_colored(f"    ✓ [D盘]Desktop.ini: {size_str(ini_size)} ({ini_count} 个)", Colors.GRAY)
    
    # Log / Logs / Cache 目录
    for dirname in ["Log", "Logs", "log", "logs", "Cache", "cache"]:
        p = os.path.join(d_root, dirname)
        if os.path.isdir(p):
            size = folder_size(p)
            if size > 0:
                engine.add_result(f"[D盘]目录-{dirname}", p, size, "D")
                print_colored(f"    ✓ [D盘]{dirname}目录: {size_str(size)}", Colors.GRAY)
    
    # Steam 缓存
    steam_patterns = [
        os.path.join(d_root, "Steam", "steamapps", "downloading"),
        os.path.join(d_root, "Program Files (x86)", "Steam", "steamapps", "downloading"),
        os.path.join(d_root, "Games", "Steam", "steamapps", "downloading"),
    ]
    for sp in steam_patterns:
        if os.path.isdir(sp):
            size = folder_size(sp)
            if size > 0:
                engine.add_result("[D盘]Steam下载缓存", sp, size, "D")
                print_colored(f"    ✓ [D盘]Steam下载缓存: {size_str(size)}", Colors.GRAY)
    
    # Backup 目录
    for bname in ["Backup", "Backups", "backup", "backups"]:
        bp = os.path.join(d_root, bname)
        if os.path.isdir(bp):
            size = folder_size(bp)
            if size > 0:
                engine.add_result(f"[D盘]备份-{bname}", bp, size, "D")
                print_colored(f"    ✓ [D盘]备份目录: {size_str(size)}", Colors.GRAY)
    
    # 旧临时文件 (30天+)
    old_patterns = ["*.log", "*.tmp", "*.bak", "*.old"]
    old_size = 0
    old_count = 0
    cutoff = time.time() - 30 * 86400
    for pattern in old_patterns:
        try:
            for f in Path(d_root).rglob(pattern):
                try:
                    if f.is_file() and f.stat().st_mtime < cutoff:
                        old_size += f.stat().st_size
                        old_count += 1
                except:
                    pass
        except:
            pass
    if old_size > 0:
        engine.add_result("[D盘]旧临时文件(30天+)", d_root, old_size, "D")
        print_colored(f"    ✓ [D盘]旧临时文件: {size_str(old_size)} ({old_count} 个)", Colors.GRAY)
    
    # 包管理器缓存
    if IS_WINDOWS:
        pkg_caches = [
            os.path.join(local_appdata, "pip", "cache"),
            os.path.join(local_appdata, "Yarn", "Cache"),
            os.path.join(os.environ.get("USERPROFILE", ""), ".nuget", "packages"),
        ]
    else:
        pkg_caches = [
            os.path.expanduser("~/.cache/pip"),
        ]
    
    for pc in pkg_caches:
        if os.path.isdir(pc):
            size = folder_size(pc)
            if size > 0:
                engine.add_result("[缓存]包管理器", pc, size, "D" if not IS_WINDOWS else "C")
                print_colored(f"    ✓ [缓存]包管理器: {size_str(size)}", Colors.GRAY)

def clean_d_drive(engine, items):
    """执行D盘清理"""
    for item in items:
        name = item["name"]
        path = item["path"]
        
        print_colored(f"    🧹 {name}...", Colors.YELLOW)
        
        if "Thumbs.db" in name:
            cleaned = 0
            base = Path(path)
            for f in base.rglob("Thumbs.db"):
                try:
                    cleaned += f.stat().st_size
                    f.unlink()
                    engine.total_files += 1
                except:
                    engine.errors += 1
        elif "Desktop.ini" in name:
            cleaned = 0
            base = Path(path)
            for f in base.rglob("desktop.ini"):
                try:
                    cleaned += f.stat().st_size
                    f.unlink()
                    engine.total_files += 1
                except:
                    engine.errors += 1
        elif "旧临时文件" in name:
            cleaned = engine.clean_old_files(path, ["*.log", "*.tmp", "*.bak", "*.old"], 30)
        elif "回收站" in name:
            cleaned = engine.clean_folder(path)
        else:
            cleaned = engine.clean_folder(path)
        
        engine.total_cleaned += cleaned
        item["status"] = "done"
        item["cleaned"] = cleaned

# ─── D盘深度分析 ─────────────────────────────────────────

def d_drive_deep_analysis():
    """D盘大文件分析"""
    d_root = "D:\\" if IS_WINDOWS else "/tmp/d_drive_test/"
    
    print()
    print_colored("╔══════════════════════════════════════════════════════╗", Colors.MAGENTA)
    print_colored("║           🔬  D盘深度分析                            ║", Colors.MAGENTA)
    print_colored("╚══════════════════════════════════════════════════════╝", Colors.MAGENTA)
    print()
    
    if not os.path.exists(d_root):
        print_colored("  ⚠ D盘不存在！", Colors.RED)
        input("  按回车返回...")
        return
    
    # 大文件扫描
    print_colored("  📦 扫描大文件 (>100MB)...", Colors.YELLOW)
    large_files = []
    
    try:
        for f in Path(d_root).rglob("*"):
            try:
                if f.is_file():
                    size = f.stat().st_size
                    if size > 100 * 1024 * 1024:
                        large_files.append((str(f), size))
            except (PermissionError, OSError):
                continue
    except:
        pass
    
    large_files.sort(key=lambda x: x[1], reverse=True)
    
    if large_files:
        print_colored(f"\n  📦 大文件 TOP {min(30, len(large_files))}:", Colors.WHITE)
        for path, size in large_files[:30]:
            display = path.replace(d_root, "")
            if len(display) > 50:
                display = "..." + display[-47:]
            print_colored(f"    {size_str(size):>12}  {display}", Colors.GRAY)
        
        total_large = sum(s for _, s in large_files)
        print_colored(f"\n  大文件总计: {size_str(total_large)}", Colors.YELLOW)
    else:
        print_colored("    未找到 >100MB 的文件", Colors.GRAY)
    
    # 空目录扫描
    print_colored("\n  📁 扫描空目录...", Colors.YELLOW)
    empty_dirs = []
    try:
        for d in Path(d_root).rglob("*"):
            try:
                if d.is_dir():
                    try:
                        next(d.iterdir())
                    except StopIteration:
                        empty_dirs.append(str(d))
            except (PermissionError, OSError):
                continue
    except:
        pass
    
    if empty_dirs:
        print_colored(f"  📁 空目录 ({len(empty_dirs)} 个，显示前20个):", Colors.WHITE)
        for d in empty_dirs[:20]:
            display = d.replace(d_root, "")
            if len(display) > 55:
                display = "..." + display[-52:]
            print_colored(f"    📂 {display}", Colors.GRAY)
    else:
        print_colored("    未找到空目录", Colors.GRAY)
    
    # 重复文件检测
    print_colored("\n  🔄 扫描重复文件...", Colors.YELLOW)
    size_groups = {}
    try:
        for f in Path(d_root).rglob("*"):
            try:
                if f.is_file() and f.stat().st_size > 1024 * 1024:  # >1MB
                    sz = f.stat().st_size
                    size_groups.setdefault(sz, []).append(str(f))
            except:
                continue
    except:
        pass
    
    duplicates = {k: v for k, v in size_groups.items() if len(v) > 1}
    if duplicates:
        print_colored(f"  🔄 发现 {len(duplicates)} 组可能的重复文件:", Colors.WHITE)
        for sz, files in sorted(duplicates.items(), key=lambda x: x[0], reverse=True)[:10]:
            print_colored(f"    {size_str(sz)}:", Colors.YELLOW)
            for f in files[:5]:
                display = f.replace(d_root, "")
                if len(display) > 50:
                    display = "..." + display[-47:]
                print_colored(f"      - {display}", Colors.GRAY)
    else:
        print_colored("    未发现重复文件", Colors.GRAY)
    
    print()
    input("  按回车返回主菜单...")

# ─── 系统优化 ────────────────────────────────────────────

def system_optimization():
    """系统优化功能"""
    print()
    print_colored("╔══════════════════════════════════════════════════════╗", Colors.BLUE)
    print_colored("║           ⚙️  系统优化                               ║", Colors.BLUE)
    print_colored("╚══════════════════════════════════════════════════════╝", Colors.BLUE)
    print()
    
    options = [
        "清理DNS缓存",
        "清理字体缓存",
        "运行磁盘清理 (cleanmgr)",
        "WinSxS 组件清理 (DISM)",
        "返回主菜单"
    ]
    
    for i, opt in enumerate(options, 1):
        print_colored(f"  [{i}] {opt}", Colors.WHITE)
    print()
    
    choice = input("  请选择: ").strip()
    
    if choice == "1":
        print_colored("\n  🔧 清理DNS缓存...", Colors.YELLOW)
        if IS_WINDOWS:
            subprocess.run(["ipconfig", "/flushdns"], capture_output=True)
        else:
            subprocess.run(["sudo", "systemd-resolve", "--flush-caches"], capture_output=True)
        print_colored("  ✅ DNS缓存已清理", Colors.GREEN)
    
    elif choice == "2":
        print_colored("\n  🔧 清理字体缓存...", Colors.YELLOW)
        if IS_WINDOWS:
            subprocess.run(["net", "stop", "FontCache"], capture_output=True)
            local_appdata = get_local_appdata()
            fc_path = os.path.join(local_appdata, "FontCache")
            if os.path.isdir(fc_path):
                for f in Path(fc_path).glob("*"):
                    try:
                        if f.is_file():
                            f.unlink()
                    except:
                        pass
            subprocess.run(["net", "start", "FontCache"], capture_output=True)
        print_colored("  ✅ 字体缓存已清理", Colors.GREEN)
    
    elif choice == "3":
        print_colored("\n  🔧 运行磁盘清理...", Colors.YELLOW)
        if IS_WINDOWS:
            subprocess.Popen(["cleanmgr", "/sagerun:1"])
            print_colored("  ✅ 磁盘清理已启动", Colors.GREEN)
        else:
            print_colored("  ⚠ 仅Windows支持", Colors.YELLOW)
    
    elif choice == "4":
        print_colored("\n  🔧 WinSxS 组件清理 (可能需要几分钟)...", Colors.YELLOW)
        if IS_WINDOWS:
            subprocess.run(["DISM", "/Online", "/Cleanup-Image", "/StartComponentCleanup"], capture_output=False)
        else:
            print_colored("  ⚠ 仅Windows支持", Colors.YELLOW)
    
    input("\n  按回车返回...")

# ─── 主界面 ──────────────────────────────────────────────

def show_menu(engine):
    """显示主菜单"""
    print()
    admin = is_admin()
    admin_str = colored("✅ 已获取", Colors.GREEN) if admin else colored("⚠️  未获取(部分功能受限)", Colors.YELLOW)
    
    c_free = drive_free_space("C")
    d_free = drive_free_space("D")
    
    print_colored("╔══════════════════════════════════════════════════════════╗", Colors.CYAN)
    print(f"║  管理员权限: {admin_str}")
    if c_free >= 0:
        print(f"║  C盘剩余: {colored(size_str(c_free), Colors.WHITE)}")
    if d_free >= 0:
        print(f"║  D盘剩余: {colored(size_str(d_free), Colors.WHITE)}")
    else:
        print(f"║  D盘: {colored('不可用', Colors.GRAY)}")
    if not IS_WINDOWS:
        print(f"║  运行环境: {colored('Linux (测试模式)', Colors.YELLOW)}")
    print_colored("╚══════════════════════════════════════════════════════════╝", Colors.CYAN)
    print()
    print_colored("  [1] 🔍 扫描可清理文件", Colors.WHITE)
    print_colored("  [2] ⚡ 一键智能清理 (推荐)", Colors.GREEN)
    print_colored("  [3] 📂 自定义选择清理", Colors.WHITE)
    print_colored("  [4] 🔬 D盘深度分析", Colors.MAGENTA)
    print_colored("  [5] ⚙️  系统优化", Colors.BLUE)
    print_colored("  [6] 🚪 退出", Colors.GRAY)
    print()

def run_scan(engine):
    """扫描所有可清理项"""
    engine.results.clear()
    
    print()
    print_colored("╔══════════════════════════════════════════════════════╗", Colors.CYAN)
    print_colored("║           🔍  正在扫描可清理的文件...               ║", Colors.CYAN)
    print_colored("╚══════════════════════════════════════════════════════╝", Colors.CYAN)
    
    scan_c_drive(engine)
    scan_d_drive(engine)
    
    total_size = sum(r["size"] for r in engine.results)
    
    # 磁盘空间
    print()
    print_colored("  💾 磁盘空间:", Colors.WHITE)
    c_free = drive_free_space("C")
    if c_free >= 0:
        try:
            _, used, free = shutil.disk_usage("C:\\" if IS_WINDOWS else "/")
            total = used + free
            print_colored(f"    C盘: 已用 {size_str(used)} / 总共 {size_str(total)} / 剩余 {size_str(free)}", Colors.GRAY)
        except:
            pass
    
    if IS_WINDOWS:
        try:
            _, used, free = shutil.disk_usage("D:\\")
            total = used + free
            print_colored(f"    D盘: 已用 {size_str(used)} / 总共 {size_str(total)} / 剩余 {size_str(free)}", Colors.GRAY)
        except:
            pass
    
    print()
    print_colored(f"  🗑️  可清理: {colored(size_str(total_size), Colors.GREEN)} 共 {len(engine.results)} 项", Colors.GREEN)
    
    return total_size

def run_cleanup(engine, items=None):
    """执行清理"""
    if items is None:
        items = engine.results
    
    if not items:
        print_colored("\n  ✨ 没有需要清理的项目", Colors.GREEN)
        return
    
    print()
    print_colored("  ⚡ 开始清理...", Colors.YELLOW)
    print()
    
    engine.total_cleaned = 0
    engine.total_files = 0
    engine.errors = 0
    
    # 分离C盘和D盘项
    c_items = [i for i in items if i["drive"] == "C"]
    d_items = [i for i in items if i["drive"] == "D"]
    
    if c_items:
        clean_c_drive(engine, c_items)
    if d_items:
        clean_d_drive(engine, d_items)
    
    # 结果
    print()
    print_colored("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", Colors.GREEN)
    print_colored("  ✅ 清理完成！", Colors.GREEN)
    print_colored(f"  📊 清理文件数: {engine.total_files} 个", Colors.WHITE)
    print_colored(f"  💾 释放空间: {colored(size_str(engine.total_cleaned), Colors.GREEN)}", Colors.WHITE)
    if engine.errors > 0:
        print_colored(f"  ⚠️  跳过文件: {engine.errors} 个 (权限不足或被占用)", Colors.YELLOW)
    print_colored("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", Colors.GREEN)

# ─── 主入口 ──────────────────────────────────────────────

def main():
    engine = CleanupEngine()
    
    while True:
        os.system("cls" if IS_WINDOWS else "clear")
        banner()
        show_menu(engine)
        
        choice = input("  请选择 (1-6): ").strip()
        
        if choice == "1":
            run_scan(engine)
            input("\n  按回车返回主菜单...")
        
        elif choice == "2":
            run_scan(engine)
            if engine.results:
                print()
                confirm = input("  确认清理? (y/n): ").strip().lower()
                if confirm == "y":
                    run_cleanup(engine)
            input("\n  按回车返回主菜单...")
        
        elif choice == "3":
            total = run_scan(engine)
            if engine.results:
                print()
                print_colored("  输入要清理的编号（逗号分隔），或输入 all 全选:", Colors.YELLOW)
                sel = input("  ").strip()
                
                if sel.lower() == "all":
                    selected = engine.results
                else:
                    try:
                        indices = [int(x.strip()) - 1 for x in sel.split(",")]
                        selected = [engine.results[i] for i in indices if 0 <= i < len(engine.results)]
                    except (ValueError, IndexError):
                        print_colored("  ⚠ 输入无效", Colors.RED)
                        input("\n  按回车返回主菜单...")
                        continue
                
                if selected:
                    run_cleanup(engine, selected)
                else:
                    print_colored("  ⚠ 未选择任何项目", Colors.YELLOW)
            input("\n  按回车返回主菜单...")
        
        elif choice == "4":
            d_drive_deep_analysis()
        
        elif choice == "5":
            system_optimization()
        
        elif choice == "6":
            print()
            print_colored("  👋 再见！", Colors.CYAN)
            time.sleep(0.5)
            break
        
        else:
            print_colored("  ⚠ 无效选择", Colors.RED)
            time.sleep(0.8)

if __name__ == "__main__":
    main()
