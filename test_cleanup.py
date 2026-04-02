#!/usr/bin/env python3
"""Win11 Cleanup Tool v2.1 - 自动化测试"""
import os
import sys
import tempfile
import shutil
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from win11_cleanup import (
    CleanupEngine, folder_size, size_str, scan_c_drive, scan_d_drive,
    clean_c_drive, clean_d_drive, is_safe_path, file_hash, progress_bar,
)

def test_size_str():
    assert "B" in size_str(500)
    assert "KB" in size_str(2048)
    assert "MB" in size_str(2 * 1024 * 1024)
    assert "GB" in size_str(2 * 1024 * 1024 * 1024)
    print("  ✅ size_str 正常")

def test_folder_size():
    test_dir = tempfile.mkdtemp()
    for i in range(5):
        with open(os.path.join(test_dir, f"test_{i}.txt"), "w") as f:
            f.write("x" * 1024)
    
    sub = os.path.join(test_dir, "sub")
    os.makedirs(sub)
    for i in range(3):
        with open(os.path.join(sub, f"sub_{i}.txt"), "w") as f:
            f.write("y" * 2048)
    
    size = folder_size(test_dir)
    expected = 5 * 1024 + 3 * 2048
    assert size == expected, f"Expected {expected}, got {size}"
    shutil.rmtree(test_dir)
    print(f"  ✅ folder_size 正常 (计算了 {size} bytes)")

def test_cleanup_engine():
    test_dir = tempfile.mkdtemp()
    
    for i in range(10):
        with open(os.path.join(test_dir, f"file_{i}.tmp"), "w") as f:
            f.write("junk" * 1000)
    
    old_file = os.path.join(test_dir, "old.log")
    with open(old_file, "w") as f:
        f.write("old" * 1000)
    os.utime(old_file, (time.time() - 40 * 86400, time.time() - 40 * 86400))
    
    sub = os.path.join(test_dir, "subdir")
    os.makedirs(sub)
    with open(os.path.join(sub, "Thumbs.db"), "w") as f:
        f.write("thumbcache" * 100)
    with open(os.path.join(sub, "desktop.ini"), "w") as f:
        f.write("[.ShellClassInfo]")
    
    before_size = folder_size(test_dir)
    print(f"    测试目录大小: {size_str(before_size)}")
    
    engine = CleanupEngine()
    cleaned = engine.clean_folder(test_dir)
    print(f"    清理文件夹: 释放 {size_str(cleaned)}")
    assert cleaned > 0, "应该清理了文件"
    
    remaining = folder_size(test_dir)
    assert remaining == 0, f"目录应为空，但还有 {remaining} bytes"
    
    shutil.rmtree(test_dir)
    print(f"  ✅ CleanupEngine.clean_folder 正常 (清理 {engine.total_files} 个文件)")

def test_scan_c_drive():
    engine = CleanupEngine()
    scan_c_drive(engine)
    print(f"  ✅ scan_c_drive 完成 (找到 {len(engine.results)} 项)")
    for r in engine.results:
        print(f"    - {r['name']}: {size_str(r['size'])}")

def test_scan_d_drive():
    engine = CleanupEngine()
    scan_d_drive(engine)
    print(f"  ✅ scan_d_drive 完成 (找到 {len(engine.results)} 项)")
    for r in engine.results:
        print(f"    - {r['name']}: {size_str(r['size'])}")
    
    if engine.results:
        d_items = [r for r in engine.results if r["drive"] == "D"]
        if d_items:
            clean_d_drive(engine, d_items)
            print(f"  ✅ D盘清理完成 (释放 {size_str(engine.total_cleaned)})")

def test_old_file_cleanup():
    test_dir = tempfile.mkdtemp()
    
    new_file = os.path.join(test_dir, "new.log")
    with open(new_file, "w") as f:
        f.write("new" * 100)
    
    old_file = os.path.join(test_dir, "old.log")
    with open(old_file, "w") as f:
        f.write("old" * 100)
    os.utime(old_file, (time.time() - 40 * 86400, time.time() - 40 * 86400))
    
    engine = CleanupEngine()
    cleaned = engine.clean_old_files(test_dir, ["*.log"], 30)
    
    assert not os.path.exists(old_file), "旧文件应被删除"
    assert os.path.exists(new_file), "新文件应保留"
    assert cleaned > 0, "应清理了旧文件"
    
    shutil.rmtree(test_dir)
    print(f"  ✅ clean_old_files 正常 (清理 {size_str(cleaned)})")

def test_pattern_cleanup():
    test_dir = tempfile.mkdtemp()
    
    for name in ["Thumbs.db", "desktop.ini", "normal.txt"]:
        with open(os.path.join(test_dir, name), "w") as f:
            f.write("test")
    
    engine = CleanupEngine()
    cleaned = engine.clean_pattern(test_dir, "Thumbs.db")
    
    assert not os.path.exists(os.path.join(test_dir, "Thumbs.db"))
    assert os.path.exists(os.path.join(test_dir, "normal.txt"))
    
    shutil.rmtree(test_dir)
    print(f"  ✅ clean_pattern 正常")

def test_is_safe_path():
    """安全路径检查测试"""
    assert is_safe_path("/tmp/test"), "/tmp 应该安全"
    assert is_safe_path("C:\\Windows\\Temp"), "Temp 应该安全"
    assert not is_safe_path("C:\\Windows\\System32"), "System32 不安全"
    assert not is_safe_path("C:\\Program Files\\app"), "Program Files 不安全"
    assert not is_safe_path("C:\\pagefile.sys"), "pagefile 不安全"
    print("  ✅ is_safe_path 正常 (拦截危险路径)")

def test_file_hash():
    """文件哈希测试"""
    test_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    test_file.write(b"hello world test content")
    test_file.close()
    
    h1 = file_hash(test_file.name)
    h2 = file_hash(test_file.name)
    
    assert h1 is not None, "应该返回哈希"
    assert h1 == h2, "同一文件哈希应一致"
    assert len(h1) == 32, "MD5 应为 32 位 hex"
    
    os.unlink(test_file.name)
    print(f"  ✅ file_hash 正常 (hash={h1[:8]}...)")

def test_progress_bar():
    """进度条测试"""
    bar = progress_bar(50, 100)
    assert "[" in bar and "]" in bar
    assert "50/100" in bar
    bar_empty = progress_bar(0, 0)
    assert "·" in bar_empty
    print("  ✅ progress_bar 正常")

def test_deleted_log():
    """删除日志记录测试"""
    test_dir = tempfile.mkdtemp()
    
    for i in range(3):
        with open(os.path.join(test_dir, f"del_{i}.tmp"), "w") as f:
            f.write("delete me")
    
    engine = CleanupEngine()
    engine.clean_folder(test_dir)
    
    assert len(engine.deleted_log) == 3, f"应记录 3 个删除，实际 {len(engine.deleted_log)}"
    
    shutil.rmtree(test_dir)
    print(f"  ✅ deleted_log 正常 (记录 {len(engine.deleted_log)} 个文件)")

if __name__ == "__main__":
    print("\n🧪 Win11 Cleanup Tool v2.1 - 测试套件\n")
    print("=" * 50)
    
    tests = [
        ("size_str", test_size_str),
        ("folder_size", test_folder_size),
        ("CleanupEngine", test_cleanup_engine),
        ("old_file_cleanup", test_old_file_cleanup),
        ("pattern_cleanup", test_pattern_cleanup),
        ("is_safe_path", test_is_safe_path),
        ("file_hash", test_file_hash),
        ("progress_bar", test_progress_bar),
        ("deleted_log", test_deleted_log),
        ("scan_c_drive", test_scan_c_drive),
        ("scan_d_drive", test_scan_d_drive),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        print(f"\n📋 测试: {name}")
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  ❌ 失败: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    green = lambda s: f"\033[92m{s}\033[0m"
    red = lambda s: f"\033[91m{s}\033[0m"
    print(f"\n{'=' * 50}")
    print(f"结果: {green(f'{passed} 通过')} / {red(f'{failed} 失败') if failed else green('0 失败')}")
    print()
    
    sys.exit(1 if failed > 0 else 0)
