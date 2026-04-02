#!/usr/bin/env python3
"""
Windows 11 垃圾清理工具 v2.1 - 独立可执行版
支持 C盘 + D盘 全面清理，含浏览器缓存、日志记录、安全防护
"""

import os
import sys
import shutil
import ctypes
import subprocess
import time
import tempfile
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict

# ─── 日志配置 ────────────────────────────────────────────
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cleanup.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger("cleanup")

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

def colored(text: str, color: str) -> str:
    return f"{color}{text}{Colors.RESET}"

def print_colored(text: str, color: str = Colors.WHITE) -> None:
    print(colored(text, color))

def banner() -> None:
    print()
    print_colored("╔══════════════════════════════════════════════════════════╗", Colors.CYAN)
    print_colored("║         🧹  Windows 11 垃圾清理工具  v2.1              ║", Colors.CYAN)
    print_colored("║        单文件独立版 — 安全清理 · 日志可溯              ║", Colors.CYAN)
    print_colored("╚══════════════════════════════════════════════════════════╝", Colors.CYAN)

# ─── 安全路径白名单 ─────────────────────────────────────
# 只允许清理以下前缀的路径，防止误删系统关键文件
SAFE_PREFIXES = [
    "temp", "tmp", "cache", "log", "logs",
    "recycle", "prefetch", "thumbcache",
    "crashdumps", "wer", "d3dscache",
    "shader", "deliveryoptimization",
    "software distribution", "inetcache",
    "recent", "nvidia", "backups",
]

def is_safe_path(path: str) -> bool:
    """检查路径是否在安全白名单内"""
    lower = path.lower()
    # 危险路径黑名单
    dangerous = [
        "windows\\system32", "windows\\syswow64",
        "program files", "programdata\\microsoft\\windows\\start menu",
        "$windows.~bt", "bootmgr", "bootnxt",
        "pagefile.sys", "hiberfil.sys", "swapfile.sys",
    ]
    for d in dangerous:
        if d in lower:
            return False
    return True

# ─── 工具函数 ────────────────────────────────────────────

def size_str(n: float) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} PB"

def folder_size(path: str) -> int:
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
            except (PermissionError, OSError) as e:
                log.debug("无法访问 %s: %s", f, e)
                continue
    except (PermissionError, OSError) as e:
        log.warning("无法扫描目录 %s: %s", path, e)
    return total

def file_hash(filepath: str, algorithm: str = "md5") -> Optional[str]:
    """计算文件哈希值，用于精确去重"""
    try:
        h = hashlib.new(algorithm)
        with open(filepath, "rb") as f:
            while chunk := f.read(8192):
                h.update(chunk)
        return h.hexdigest()
    except (PermissionError, OSError, ValueError):
        return None

def drive_free_space(drive: str) -> int:
    """获取磁盘剩余空间"""
    if not IS_WINDOWS:
        if drive == "C":
            try:
                return shutil.disk_usage("/").free
            except OSError:
                return -1
        elif drive == "D":
            try:
                return shutil.disk_usage("/tmp").free
            except OSError:
                return -1
        return -1
    try:
        _, _, free = shutil.disk_usage(f"{drive}:\\")
        return free
    except OSError as e:
        log.debug("无法获取 %s 盘空间: %s", drive, e)
        return -1

def is_admin() -> bool:
    """检查管理员权限"""
    if not IS_WINDOWS:
        return os.geteuid() == 0
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except (AttributeError, OSError):
        return False

def get_temp_dir() -> str:
    if IS_WINDOWS:
        return os.environ.get("TEMP", os.environ.get("TMP", r"C:\Windows\Temp"))
    return tempfile.gettempdir()

def get_local_appdata() -> str:
    if IS_WINDOWS:
        return os.environ.get("LOCALAPPDATA", "")
    return os.path.expanduser("~/.local/share")

def get_appdata() -> str:
    if IS_WINDOWS:
        return os.environ.get("APPDATA", "")
    return os.path.expanduser("~/.config")

def get_user_profile() -> str:
    if IS_WINDOWS:
        return os.environ.get("USERPROFILE", "")
    return os.path.expanduser("~")

def progress_bar(current: int, total: int, width: int = 30) -> str:
    """生成文本进度条"""
    if total == 0:
        return "[" + "·" * width + "]"
    filled = int(width * current / total)
    bar = "█" * filled + "·" * (width - filled)
    return f"[{bar}] {current}/{total}"

# ─── 核心清理引擎 ────────────────────────────────────────

class CleanupEngine:
    def __init__(self):
        self.total_cleaned: int = 0
        self.total_files: int = 0
        self.errors: int = 0
        self.results: list[dict] = []
        self.deleted_log: list[str] = []  # 记录所有删除的文件路径
    
    def clean_folder(self, path: str, filter_ext: Optional[list[str]] = None) -> int:
        """清理目录内容，返回清理的字节数"""
        if not is_safe_path(path):
            log.warning("路径未通过安全检查，跳过: %s", path)
            return 0
        
        cleaned = 0
        p = Path(path)
        if not p.exists():
            return 0
        
        try:
            items = list(p.rglob("*"))
            total = len(items)
            
            for idx, item in enumerate(items):
                try:
                    if filter_ext and item.is_file() and item.suffix.lower() not in filter_ext:
                        continue
                    if item.is_file():
                        size = item.stat().st_size
                        item.unlink(missing_ok=True)
                        cleaned += size
                        self.total_files += 1
                        self.deleted_log.append(str(item))
                        log.info("已删除: %s (%s)", item, size_str(size))
                    elif item.is_dir():
                        try:
                            item.rmdir()
                        except OSError:
                            pass  # 非空目录，跳过
                except (PermissionError, OSError) as e:
                    self.errors += 1
                    log.warning("删除失败: %s - %s", item, e)
                    continue
            
            # 再次尝试清理空目录（从深层到浅层）
            for item in sorted(p.rglob("*"), key=lambda x: len(str(x)), reverse=True):
                if item.is_dir():
                    try:
                        item.rmdir()
                    except OSError:
                        pass
        except (PermissionError, OSError) as e:
            self.errors += 1
            log.error("清理目录失败 %s: %s", path, e)
        
        return cleaned
    
    def clean_pattern(self, base_path: str, pattern: str) -> int:
        """清理匹配模式的文件"""
        if not is_safe_path(base_path):
            log.warning("路径未通过安全检查，跳过: %s", base_path)
            return 0
        
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
                        self.deleted_log.append(str(item))
                        log.info("已删除 (模式匹配): %s", item)
                except (PermissionError, OSError) as e:
                    self.errors += 1
                    log.warning("删除失败: %s - %s", item, e)
                    continue
        except (PermissionError, OSError) as e:
            log.error("模式扫描失败 %s/%s: %s", base_path, pattern, e)
        
        return cleaned
    
    def clean_old_files(self, base_path: str, patterns: list[str], days: int = 30) -> int:
        """清理指定天数以上的文件"""
        if not is_safe_path(base_path):
            log.warning("路径未通过安全检查，跳过: %s", base_path)
            return 0
        
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
                                self.deleted_log.append(str(item))
                                log.info("已删除 (旧文件 %d天+): %s", days, item)
                    except (PermissionError, OSError) as e:
                        self.errors += 1
                        log.warning("删除失败: %s - %s", item, e)
                        continue
            except (PermissionError, OSError) as e:
                log.error("旧文件扫描失败 %s/%s: %s", base_path, pattern, e)
        
        return cleaned
    
    def add_result(self, name: str, path: str, size: int, drive: str, status: str = "found") -> None:
        self.results.append({
            "name": name, "path": path, "size": size,
            "drive": drive, "status": status
        })

# ─── 浏览器缓存清理 (新增) ──────────────────────────────

def scan_browser_cache(engine: CleanupEngine) -> None:
    """扫描浏览器缓存（Chrome / Edge / Firefox）"""
    local_appdata = get_local_appdata()
    user_profile = get_user_profile()
    
    browsers = []
    
    if IS_WINDOWS:
        browsers = [
            ("Chrome 缓存", os.path.join(local_appdata, r"Google\Chrome\User Data\Default\Cache\Cache_Data")),
            ("Chrome Service Worker", os.path.join(local_appdata, r"Google\Chrome\User Data\Default\Service Worker\CacheStorage")),
            ("Edge 缓存", os.path.join(local_appdata, r"Microsoft\Edge\User Data\Default\Cache\Cache_Data")),
            ("Edge Service Worker", os.path.join(local_appdata, r"Microsoft\Edge\User Data\Default\Service Worker\CacheStorage")),
            ("Firefox 缓存", os.path.join(local_appdata, r"Mozilla\Firefox\Profiles")),
        ]
    else:
        browsers = [
            ("Chrome 缓存", os.path.join(user_profile, ".cache/google-chrome/Default/Cache")),
            ("Firefox 缓存", os.path.join(user_profile, ".cache/mozilla/firefox")),
        ]
    
    print_colored("  🌐 [浏览器] 扫描中...", Colors.YELLOW)
    
    for name, path in browsers:
        if not path:
            continue
        # Firefox Profiles 是多层目录，特殊处理
        if "Firefox" in name and "Profiles" in path:
            if os.path.isdir(path):
                total_size = 0
                try:
                    for profile in Path(path).iterdir():
                        if profile.is_dir():
                            cache_dir = profile / "cache2" / "entries"
                            if cache_dir.exists():
                                total_size += folder_size(str(cache_dir))
                            # 也清理 startupCache
                            startup = profile / "startupCache"
                            if startup.exists():
                                total_size += folder_size(str(startup))
                except OSError:
                    pass
                if total_size > 0:
                    engine.add_result(name, path, total_size, "C")
                    print_colored(f"    ✓ {name}: {size_str(total_size)}", Colors.GRAY)
            continue
        
        size = folder_size(path)
        if size > 0:
            engine.add_result(name, path, size, "C")
            print_colored(f"    ✓ {name}: {size_str(size)}", Colors.GRAY)

def clean_browser_cache(engine: CleanupEngine, items: list[dict]) -> None:
    """清理浏览器缓存"""
    for item in items:
        name = item["name"]
        path = item["path"]
        
        print_colored(f"    🧹 {name}...", Colors.YELLOW)
        log.info("开始清理浏览器缓存: %s", name)
        
        if "Firefox" in name and "Profiles" in path:
            # Firefox 特殊处理
            cleaned = 0
            try:
                for profile in Path(path).iterdir():
                    if profile.is_dir():
                        for subdir in ["cache2/entries", "startupCache"]:
                            sp = profile / subdir
                            if sp.exists():
                                cleaned += engine.clean_folder(str(sp))
            except OSError as e:
                log.warning("Firefox 缓存清理失败: %s", e)
        else:
            cleaned = engine.clean_folder(path)
        
        engine.total_cleaned += cleaned
        item["status"] = "done"
        item["cleaned"] = cleaned

# ─── C盘清理项 ──────────────────────────────────────────

def scan_c_drive(engine: CleanupEngine) -> None:
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

def clean_c_drive(engine: CleanupEngine, items: list[dict]) -> None:
    """执行C盘清理"""
    for item in items:
        name = item["name"]
        path = item["path"]
        
        if not is_safe_path(path):
            log.warning("安全检查未通过，跳过: %s", path)
            continue
        
        print_colored(f"    🧹 {name}...", Colors.YELLOW)
        log.info("开始清理: %s (%s)", name, path)
        
        cleaned = 0
        
        if name in ("Windows更新缓存", "Delivery优化文件"):
            service_stopped = False
            if IS_WINDOWS:
                try:
                    result = subprocess.run(
                        ["net", "stop", "wuauserv"],
                        capture_output=True, timeout=10, text=True
                    )
                    service_stopped = result.returncode == 0
                    if service_stopped:
                        time.sleep(0.5)
                    else:
                        log.warning("无法停止 wuauserv: %s", result.stderr)
                except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                    log.warning("停止服务异常: %s", e)
            
            cleaned = engine.clean_folder(path)
            
            if IS_WINDOWS and service_stopped:
                try:
                    subprocess.run(
                        ["net", "start", "wuauserv"],
                        capture_output=True, timeout=10
                    )
                    log.info("wuauserv 已重启")
                except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                    log.error("重启 wuauserv 失败: %s", e)
                    print_colored("    ⚠️  wuauserv 重启失败，请手动检查", Colors.RED)
        elif "缩略图" in name:
            cleaned = engine.clean_pattern(path, "thumbcache_*")
        elif "NVIDIA" in name or "着色器" in name:
            cleaned = engine.clean_folder(path)
        else:
            cleaned = engine.clean_folder(path)
        
        engine.total_cleaned += cleaned
        item["status"] = "done"
        item["cleaned"] = cleaned

# ─── D盘清理项 ──────────────────────────────────────────

def scan_d_drive(engine: CleanupEngine) -> None:
    """扫描D盘可清理项"""
    if IS_WINDOWS:
        d_root = "D:\\"
    else:
        d_root = "/tmp/d_drive_test/"
        os.makedirs(d_root, exist_ok=True)
        test_dirs = ["Temp", "Logs", "Cache", "Backup"]
        for td in test_dirs:
            tp = os.path.join(d_root, td)
            os.makedirs(tp, exist_ok=True)
            for i in range(3):
                with open(os.path.join(tp, f"test_{i}.tmp"), "w") as f:
                    f.write("x" * 1024 * (i + 1) * 100)
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
    print_colored("    ...扫描 Thumbs.db", Colors.GRAY)
    thumbs_size = 0
    thumbs_count = 0
    try:
        for f in Path(d_root).rglob("Thumbs.db"):
            try:
                thumbs_size += f.stat().st_size
                thumbs_count += 1
            except OSError:
                pass
    except OSError:
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
            except OSError:
                pass
    except OSError:
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
                except OSError:
                    pass
        except OSError:
            pass
    if old_size > 0:
        engine.add_result("[D盘]旧临时文件(30天+)", d_root, old_size, "D")
        print_colored(f"    ✓ [D盘]旧临时文件: {size_str(old_size)} ({old_count} 个)", Colors.GRAY)
    
    # 包管理器缓存
    if IS_WINDOWS:
        user_profile = get_user_profile()
        local_appdata = get_local_appdata()
        pkg_caches = [
            ("pip 缓存", os.path.join(local_appdata, "pip", "cache")),
            ("Yarn 缓存", os.path.join(local_appdata, "Yarn", "Cache")),
            ("NuGet 缓存", os.path.join(user_profile, ".nuget", "packages")),
            ("Cargo 缓存", os.path.join(user_profile, ".cargo", "registry")),
        ]
    else:
        pkg_caches = [
            ("pip 缓存", os.path.expanduser("~/.cache/pip")),
        ]
    
    for pkg_name, pc in pkg_caches:
        if os.path.isdir(pc):
            size = folder_size(pc)
            if size > 0:
                drive = "C" if IS_WINDOWS else "D"
                engine.add_result(f"[缓存]{pkg_name}", pc, size, drive)
                print_colored(f"    ✓ [缓存]{pkg_name}: {size_str(size)}", Colors.GRAY)

def clean_d_drive(engine: CleanupEngine, items: list[dict]) -> None:
    """执行D盘清理"""
    for item in items:
        name = item["name"]
        path = item["path"]
        
        print_colored(f"    🧹 {name}...", Colors.YELLOW)
        log.info("开始清理 D盘项: %s (%s)", name, path)
        
        cleaned = 0
        
        if "Thumbs.db" in name:
            base = Path(path)
            for f in base.rglob("Thumbs.db"):
                try:
                    size = f.stat().st_size
                    f.unlink()
                    cleaned += size
                    engine.total_files += 1
                    engine.deleted_log.append(str(f))
                    log.info("已删除: %s", f)
                except OSError as e:
                    engine.errors += 1
                    log.warning("删除失败: %s - %s", f, e)
        elif "Desktop.ini" in name:
            base = Path(path)
            for f in base.rglob("desktop.ini"):
                try:
                    size = f.stat().st_size
                    f.unlink()
                    cleaned += size
                    engine.total_files += 1
                    engine.deleted_log.append(str(f))
                    log.info("已删除: %s", f)
                except OSError as e:
                    engine.errors += 1
                    log.warning("删除失败: %s - %s", f, e)
        elif "旧临时文件" in name:
            cleaned = engine.clean_old_files(path, ["*.log", "*.tmp", "*.bak", "*.old"], 30)
        elif "回收站" in name:
            cleaned = engine.clean_folder(path)
        else:
            cleaned = engine.clean_folder(path)
        
        engine.total_cleaned += cleaned
        item["status"] = "done"
        item["cleaned"] = cleaned

# ─── D盘深度分析 (改进：哈希去重) ───────────────────────

def d_drive_deep_analysis() -> None:
    """D盘大文件分析（含哈希精确去重）"""
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
    except OSError:
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
    except OSError:
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
    
    # 改进的重复文件检测：先按大小分组，再用 MD5 精确比对
    print_colored("\n  🔄 扫描重复文件（精确哈希比对）...", Colors.YELLOW)
    size_groups: dict[int, list[str]] = defaultdict(list)
    
    try:
        for f in Path(d_root).rglob("*"):
            try:
                if f.is_file() and f.stat().st_size > 1024 * 1024:  # >1MB
                    size_groups[f.stat().st_size].append(str(f))
            except OSError:
                continue
    except OSError:
        pass
    
    # 对同大小文件计算哈希
    true_duplicates: dict[str, list[str]] = defaultdict(list)
    duplicate_count = 0
    
    for sz, files in size_groups.items():
        if len(files) < 2:
            continue
        for fpath in files:
            h = file_hash(fpath)
            if h:
                true_duplicates[h].append(fpath)
    
    # 过滤出真正的重复文件（哈希相同且数量>1）
    real_dupes = {h: paths for h, paths in true_duplicates.items() if len(paths) > 1}
    duplicate_count = len(real_dupes)
    
    if real_dupes:
        print_colored(f"  🔄 发现 {duplicate_count} 组重复文件（MD5 精确匹配）:", Colors.WHITE)
        for h, paths in sorted(real_dupes.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
            sz = os.path.getsize(paths[0])
            print_colored(f"    {size_str(sz)} ({len(paths)} 个文件):", Colors.YELLOW)
            for fp in paths[:5]:
                display = fp.replace(d_root, "")
                if len(display) > 50:
                    display = "..." + display[-47:]
                print_colored(f"      - {display}", Colors.GRAY)
    else:
        print_colored("    未发现重复文件", Colors.GRAY)
    
    print()
    input("  按回车返回主菜单...")

# ─── 系统优化 ────────────────────────────────────────────

def system_optimization() -> None:
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
    log.info("系统优化选择: %s", choice)
    
    if choice == "1":
        print_colored("\n  🔧 清理DNS缓存...", Colors.YELLOW)
        try:
            if IS_WINDOWS:
                subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=10)
            else:
                subprocess.run(["sudo", "systemd-resolve", "--flush-caches"], capture_output=True, timeout=10)
            print_colored("  ✅ DNS缓存已清理", Colors.GREEN)
            log.info("DNS缓存已清理")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print_colored(f"  ❌ DNS清理失败: {e}", Colors.RED)
            log.error("DNS清理失败: %s", e)
    
    elif choice == "2":
        print_colored("\n  🔧 清理字体缓存...", Colors.YELLOW)
        try:
            if IS_WINDOWS:
                subprocess.run(["net", "stop", "FontCache"], capture_output=True, timeout=10)
                local_appdata = get_local_appdata()
                fc_path = os.path.join(local_appdata, "FontCache")
                if os.path.isdir(fc_path):
                    for f in Path(fc_path).glob("*"):
                        try:
                            if f.is_file():
                                f.unlink()
                        except OSError:
                            pass
                subprocess.run(["net", "start", "FontCache"], capture_output=True, timeout=10)
            print_colored("  ✅ 字体缓存已清理", Colors.GREEN)
            log.info("字体缓存已清理")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print_colored(f"  ❌ 字体缓存清理失败: {e}", Colors.RED)
            log.error("字体缓存清理失败: %s", e)
    
    elif choice == "3":
        print_colored("\n  🔧 运行磁盘清理...", Colors.YELLOW)
        if IS_WINDOWS:
            try:
                subprocess.Popen(["cleanmgr", "/sagerun:1"])
                print_colored("  ✅ 磁盘清理已启动", Colors.GREEN)
            except FileNotFoundError:
                print_colored("  ❌ cleanmgr 不可用", Colors.RED)
        else:
            print_colored("  ⚠ 仅Windows支持", Colors.YELLOW)
    
    elif choice == "4":
        print_colored("\n  🔧 WinSxS 组件清理 (可能需要几分钟)...", Colors.YELLOW)
        if IS_WINDOWS:
            try:
                subprocess.run(
                    ["DISM", "/Online", "/Cleanup-Image", "/StartComponentCleanup"],
                    capture_output=False, timeout=600
                )
            except subprocess.TimeoutExpired:
                print_colored("  ⚠ DISM 执行超时", Colors.YELLOW)
        else:
            print_colored("  ⚠ 仅Windows支持", Colors.YELLOW)
    
    input("\n  按回车返回...")

# ─── 主界面 ──────────────────────────────────────────────

def show_menu(engine: CleanupEngine) -> None:
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
    print_colored("  [6] 📋 查看清理日志", Colors.GRAY)
    print_colored("  [7] 🚪 退出", Colors.GRAY)
    print()

def run_scan(engine: CleanupEngine) -> int:
    """扫描所有可清理项"""
    engine.results.clear()
    
    print()
    print_colored("╔══════════════════════════════════════════════════════╗", Colors.CYAN)
    print_colored("║           🔍  正在扫描可清理的文件...               ║", Colors.CYAN)
    print_colored("╚══════════════════════════════════════════════════════╝", Colors.CYAN)
    
    scan_c_drive(engine)
    scan_browser_cache(engine)  # 新增：浏览器缓存
    scan_d_drive(engine)
    
    total_size = sum(r["size"] for r in engine.results)
    
    print()
    print_colored("  💾 磁盘空间:", Colors.WHITE)
    try:
        if IS_WINDOWS:
            _, used, free = shutil.disk_usage("C:\\")
        else:
            _, used, free = shutil.disk_usage("/")
        total = used + free
        print_colored(f"    C盘: 已用 {size_str(used)} / 总共 {size_str(total)} / 剩余 {size_str(free)}", Colors.GRAY)
    except OSError:
        pass
    
    if IS_WINDOWS:
        try:
            _, used, free = shutil.disk_usage("D:\\")
            total = used + free
            print_colored(f"    D盘: 已用 {size_str(used)} / 总共 {size_str(total)} / 剩余 {size_str(free)}", Colors.GRAY)
        except OSError:
            pass
    
    print()
    print_colored(f"  🗑️  可清理: {colored(size_str(total_size), Colors.GREEN)} 共 {len(engine.results)} 项", Colors.GREEN)
    
    log.info("扫描完成: %d 项, 共 %s", len(engine.results), size_str(total_size))
    
    return total_size

def run_cleanup(engine: CleanupEngine, items: Optional[list[dict]] = None) -> None:
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
    
    # 分离浏览器、C盘和D盘项
    browser_items = [i for i in items if "缓存" in i["name"] and any(b in i["name"] for b in ["Chrome", "Edge", "Firefox"])]
    c_items = [i for i in items if i["drive"] == "C" and i not in browser_items]
    d_items = [i for i in items if i["drive"] == "D"]
    
    if browser_items:
        clean_browser_cache(engine, browser_items)
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
    print_colored(f"  📋 操作日志: {LOG_FILE}", Colors.GRAY)
    print_colored("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", Colors.GREEN)
    
    log.info("清理完成: %d 文件, 释放 %s, %d 错误", engine.total_files, size_str(engine.total_cleaned), engine.errors)

def show_log() -> None:
    """显示清理日志"""
    print()
    print_colored("╔══════════════════════════════════════════════════════╗", Colors.GRAY)
    print_colored("║           📋  清理日志                              ║", Colors.GRAY)
    print_colored("╚══════════════════════════════════════════════════════╝", Colors.GRAY)
    print()
    
    if not os.path.exists(LOG_FILE):
        print_colored("  暂无日志记录", Colors.GRAY)
        input("\n  按回车返回...")
        return
    
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        if not lines:
            print_colored("  日志为空", Colors.GRAY)
        else:
            # 显示最后 50 行
            display_lines = lines[-50:]
            for line in display_lines:
                line = line.rstrip()
                if "[ERROR]" in line:
                    print_colored(f"  {line}", Colors.RED)
                elif "[WARNING]" in line:
                    print_colored(f"  {line}", Colors.YELLOW)
                elif "已删除" in line:
                    print_colored(f"  {line}", Colors.GRAY)
                else:
                    print_colored(f"  {line}", Colors.WHITE)
            
            if len(lines) > 50:
                print_colored(f"\n  ... (共 {len(lines)} 行，显示最后 50 行)", Colors.GRAY)
    except OSError as e:
        print_colored(f"  读取日志失败: {e}", Colors.RED)
    
    print()
    input("  按回车返回主菜单...")

# ─── 主入口 ──────────────────────────────────────────────

def main() -> None:
    engine = CleanupEngine()
    
    log.info("=" * 50)
    log.info("清理工具启动 v2.1")
    log.info("系统: %s, 管理员: %s", sys.platform, is_admin())
    
    while True:
        os.system("cls" if IS_WINDOWS else "clear")
        banner()
        show_menu(engine)
        
        choice = input("  请选择 (1-7): ").strip()
        log.info("用户选择: %s", choice)
        
        if choice == "1":
            run_scan(engine)
            input("\n  按回车返回主菜单...")
        
        elif choice == "2":
            run_scan(engine)
            if engine.results:
                print()
                confirm = input("  确认清理? (y/n): ").strip().lower()
                if confirm == "y":
                    log.info("用户确认一键清理")
                    run_cleanup(engine)
                else:
                    log.info("用户取消清理")
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
                    log.info("用户选择清理 %d 项", len(selected))
                    run_cleanup(engine, selected)
                else:
                    print_colored("  ⚠ 未选择任何项目", Colors.YELLOW)
            input("\n  按回车返回主菜单...")
        
        elif choice == "4":
            d_drive_deep_analysis()
        
        elif choice == "5":
            system_optimization()
        
        elif choice == "6":
            show_log()
        
        elif choice == "7":
            print()
            print_colored("  👋 再见！", Colors.CYAN)
            log.info("清理工具退出")
            time.sleep(0.5)
            break
        
        else:
            print_colored("  ⚠ 无效选择", Colors.RED)
            time.sleep(0.8)

if __name__ == "__main__":
    main()
