#!/usr/bin/env python3
"""
树剪 TreeCut — 打包为独立 .exe 安装包
用法:
  pip install pyinstaller
  python build_exe.py
输出:
  dist/树剪TreeCut.exe  (单文件)
"""
import subprocess, sys, shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"

def build():
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)

    icon_path = PROJECT_ROOT / "tree_icon.ico"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=树剪TreeCut",
        "--windowed",
        "--onefile",
        f"--add-data={PROJECT_ROOT / 'protected_words.json'}{';.'}",
        f"--add-data={PROJECT_ROOT / '.env.example'}{';.'}",
        f"--add-data={PROJECT_ROOT / 'tree_icon.ico'}{';.'}",
        "--hidden-import=core",
        "--hidden-import=core.config",
        "--hidden-import=core.pipeline",
        "--hidden-import=core.copywriter",
        "--hidden-import=core.tts",
        "--hidden-import=core.draft",
        "--hidden-import=core.scanner",
        "--hidden-import=ui.desktop",
        "--hidden-import=ui.web",
        "--hidden-import=utils.security",
        "--hidden-import=utils.retry",
        "--hidden-import=utils.quality_scorer",
        "--hidden-import=utils.knowledge",
        "--hidden-import=utils.logging",
        "--hidden-import=review_audit",
        "--hidden-import=edge_tts",
        "--hidden-import=openai",
        "--hidden-import=cv2",
        "--hidden-import=numpy",
        "--hidden-import=PIL",
        "--hidden-import=sqlite3",
        "--hidden-import=asyncio",
        "--collect-all=edge_tts",
        "--collect-all=pyJianYingDraft",
    ]

    if icon_path.exists():
        cmd.append(f"--icon={icon_path}")

    cmd.append(str(PROJECT_ROOT / "树剪.py"))

    print("=" * 60)
    print("  树剪 TreeCut — PyInstaller 打包")
    print("=" * 60)
    print(f"  输出目录: {DIST_DIR}")

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if result.returncode == 0:
        exe = DIST_DIR / "树剪TreeCut.exe"
        size_mb = exe.stat().st_size / (1024 * 1024) if exe.exists() else 0
        print(f"\n  ✅ 打包完成: {exe} ({size_mb:.0f}MB)")
        print(f"\n  分发时需附带 .env / ai_material_library.db / 02_BGM/")
    else:
        print(f"\n  ❌ 打包失败 (退出码: {result.returncode})")

if __name__ == "__main__":
    build()
