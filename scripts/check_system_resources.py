#!/usr/bin/env python3
"""系统资源诊断 — 内存/磁盘/GPU/数据库完整性"""
import sys, os, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

print("=" * 55)
print("  系统资源诊断")
print("=" * 55)

# ── 内存 ──
try:
    import psutil
    mem = psutil.virtual_memory()
    print(f"  总内存:    {mem.total/1e9:.1f} GB")
    print(f"  可用内存:  {mem.available/1e9:.1f} GB")
    print(f"  使用率:    {mem.percent:.0f}% {'[OK]' if mem.percent < 85 else '[WARN] 内存紧张'}")
except ImportError:
    print("  [WARN] psutil 未安装 (pip install psutil)")

# ── 磁盘 ──
import shutil
proj = Path(__file__).parent.parent
usage = shutil.disk_usage(proj)
print(f"\n  项目磁盘: {proj}")
print(f"  总空间:    {usage.total/1e9:.1f} GB")
print(f"  可用空间:  {usage.free/1e9:.1f} GB")
print(f"  使用率:    {(1-usage.free/usage.total)*100:.0f}%")

# ── GPU ──
try:
    import torch
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            free, total = torch.cuda.mem_get_info(i)
            print(f"\n  GPU {i}: {props.name}")
            print(f"    总显存:  {total/1e9:.1f} GB")
            print(f"    可用:    {free/1e9:.1f} GB")
    else:
        print("\n  GPU: 无 (CPU模式)")
except ImportError:
    print("\n  [INFO] torch 未安装 — 仅 CPU 模式")

# ── 数据库 ──
db_path = proj / "ai_material_library.db"
if db_path.exists():
    size_mb = db_path.stat().st_size / 1e6
    print(f"\n  数据库: {db_path}")
    print(f"  大小:     {size_mb:.1f} MB")
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA integrity_check")
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print(f"  完整性:   [OK]")
        print(f"  表数:     {len(tables)}")
        for t in tables:
            cnt = conn.execute(f"SELECT COUNT(*) FROM {t[0]}").fetchone()[0]
            print(f"    {t[0]:30s} {cnt:>8,} 行")
        conn.close()
    except Exception as e:
        print(f"  完整性:   [FAIL] {e}")
else:
    print("\n  [WARN] ai_material_library.db 不存在")

print("=" * 55)
print("  诊断完成")
