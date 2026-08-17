"""
树剪 TreeCut v11.2 — 全盘视频扫描器
====================================
递归扫描所有磁盘或指定目录，定位全部视频文件。
支持断点续扫（记录最后扫描位置）、权限错误容错。
"""

import os
import json
import time
from pathlib import Path
from typing import List, Optional, Iterator, Callable
from datetime import datetime

_PROJ_ROOT = Path(__file__).parent.parent
_CHECKPOINT_FILE = _PROJ_ROOT / "scan_checkpoint.json"

# 默认跳过目录（Windows系统目录）
DEFAULT_EXCLUDE_DIRS = [
    "Windows", "Program Files", "Program Files (x86)", "ProgramData",
    "AppData", "System Volume Information", "$Recycle.Bin",
    "$RECYCLE.BIN", "Recovery", "System32", "WinSxS",
    "Python", "node_modules", ".git", "__pycache__",
    ".cache", ".npm", ".cargo", ".rustup", ".local",
    "Temp", "tmp", "cache", "Cache",
]

# 支持的视频扩展名
DEFAULT_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".3gp"}


def get_all_drives() -> List[str]:
    """获取Windows系统所有可用盘符"""
    drives = []
    try:
        import string
        from ctypes import windll
        bitmask = windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drive = f"{letter}:\\"
                # 检查磁盘是否就绪
                try:
                    if os.path.exists(drive):
                        drives.append(drive)
                except Exception:
                    pass
            bitmask >>= 1
    except Exception:
        # 回退：尝试 A-Z 盘符
        import string
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            try:
                if os.path.exists(drive):
                    drives.append(drive)
            except Exception:
                pass
    return drives


def scan_directory_tree(
    root_dir: str,
    extensions: set = None,
    exclude_dirs: list = None,
    max_depth: int = 20,
    progress_callback: Callable = None,
    cancel_event = None,
) -> Iterator[str]:
    """
    递归扫描目录树，生成所有视频文件路径。

    参数:
        root_dir: 根目录路径
        extensions: 视频扩展名集合
        exclude_dirs: 跳过的目录名列表（不区分大小写）
        max_depth: 最大递归深度
        progress_callback: 进度回调 (dir_count, file_count)
        cancel_event: threading.Event，设为True可中断扫描
    """
    if extensions is None:
        extensions = DEFAULT_VIDEO_EXTENSIONS
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDE_DIRS

    exclude_lower = {d.lower() for d in exclude_dirs}
    dir_count = 0
    file_count = 0

    try:
        for entry in os.scandir(root_dir):
            if cancel_event and cancel_event.is_set():
                return

            try:
                if entry.is_dir(follow_symlinks=False):
                    dir_count += 1
                    name_lower = entry.name.lower()
                    # 跳过系统/隐藏目录
                    if name_lower in exclude_lower:
                        continue
                    if name_lower.startswith("."):
                        continue
                    if max_depth > 0:
                        yield from scan_directory_tree(
                            entry.path, extensions, exclude_dirs,
                            max_depth - 1, progress_callback, cancel_event
                        )
                elif entry.is_file(follow_symlinks=False):
                    file_count += 1
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext in extensions:
                        yield entry.path

            except (PermissionError, OSError):
                continue

        if progress_callback and dir_count > 0:
            progress_callback(dir_count, file_count)

    except (PermissionError, OSError):
        pass


def iter_all_videos(
    root_paths: List[str] = None,
    extensions: set = None,
    exclude_dirs: list = None,
    progress_callback: Callable = None,
    cancel_event = None,
) -> Iterator[str]:
    """
    迭代所有视频文件。

    参数:
        root_paths: 根目录列表。None = 全盘扫描。
        extensions: 视频扩展名。None = 默认扩展名。
        exclude_dirs: 跳过的目录名列表。
        progress_callback: 进度回调 (current_dir, total_files_found)。
        cancel_event: 中断事件。
    """
    if extensions is None:
        extensions = DEFAULT_VIDEO_EXTENSIONS
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDE_DIRS

    if root_paths is None:
        root_paths = get_all_drives()

    for root in root_paths:
        if not os.path.exists(root):
            continue
        if cancel_event and cancel_event.is_set():
            return
        try:
            yield from scan_directory_tree(
                root, extensions, exclude_dirs,
                max_depth=20, progress_callback=progress_callback,
                cancel_event=cancel_event
            )
        except Exception:
            continue


def count_videos_in_dir(
    root_paths: List[str],
    extensions: set = None,
    exclude_dirs: list = None,
    max_count: int = 0,
) -> int:
    """快速估算目录中的视频数量（不递归全展开，仅做粗略统计）"""
    if extensions is None:
        extensions = DEFAULT_VIDEO_EXTENSIONS
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDE_DIRS

    count = 0
    exclude_lower = {d.lower() for d in exclude_dirs}

    for root in root_paths:
        if not os.path.exists(root):
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                # 过滤排除目录
                dirnames[:] = [d for d in dirnames
                              if d.lower() not in exclude_lower
                              and not d.startswith(".")]
                for f in filenames:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in extensions:
                        count += 1
                        if max_count and count >= max_count:
                            return count
        except (PermissionError, OSError):
            continue
    return count


# ═══════════════════════════════════════════════════════════════
# 断点续扫
# ═══════════════════════════════════════════════════════════════

def load_scan_checkpoint() -> dict:
    """加载上次扫描断点"""
    if _CHECKPOINT_FILE.exists():
        try:
            return json.loads(_CHECKPOINT_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            pass
    return {
        "last_path": None,
        "scanned_count": 0,
        "discovered_count": 0,
        "timestamp": None,
    }


def save_scan_checkpoint(last_path: str, scanned_count: int, discovered_count: int):
    """保存扫描断点"""
    try:
        data = {
            "last_path": last_path,
            "scanned_count": scanned_count,
            "discovered_count": discovered_count,
            "timestamp": datetime.now().isoformat(),
        }
        _CHECKPOINT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def clear_scan_checkpoint():
    """清除断点"""
    try:
        _CHECKPOINT_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def get_video_file_info(video_path: str) -> dict:
    """获取视频文件基本信息（大小、修改时间）"""
    try:
        stat = os.stat(video_path)
        return {
            "size_mb": stat.st_size / (1024 * 1024),
            "file_mtime": stat.st_mtime,
            "file_size": stat.st_size,
        }
    except Exception:
        return {"size_mb": 0, "file_mtime": 0, "file_size": 0}
