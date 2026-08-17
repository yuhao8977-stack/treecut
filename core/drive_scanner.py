"""
树剪 — 全盘驱动器扫描引擎 (v10.4 静默版)
win32api获取盘符 + 懒加载目录树 + 视频元数据提取(无弹窗)
"""
import os, sys, json, time, threading
from pathlib import Path
from typing import List, Dict, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.silent_subprocess import run as _silent_run

import platform as _platform
IS_WINDOWS = _platform.system() == "Windows"
try:
    import win32api; HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    if IS_WINDOWS:
        pass  # 静默 — 不弹窗提示

def open_file_explorer(path: str):
    """Open file explorer at path. If path is a file, open its containing folder."""
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    if IS_WINDOWS: os.startfile(folder)
    elif _platform.system() == "Darwin": _silent_run(["open", folder])
    else: _silent_run(["xdg-open", folder])

VIDEO_EXT = {'.mp4','.mov','.avi','.mkv','.webm','.flv','.wmv','.m4v','.mpg','.mpeg'}


class DriveEntry:
    def __init__(self, name, path, is_drive=False, video_count=0):
        self.name = name; self.path = path
        self.is_drive = is_drive; self.video_count = video_count
        self.children = []; self.loaded = False


class VideoEntry:
    def __init__(self, path):
        self.path = path; self.name = Path(path).name
        self.size_mb = 0; self.duration_str = "-"; self.duration_sec = 0
        self.fps = 0; self.width = 0; self.height = 0
        self.resolution = "-"; self._probed = False

    def probe(self):
        """静默获取视频元数据 — 不弹窗"""
        if self._probed: return
        try:
            stat = os.stat(self.path)
            self.size_mb = round(stat.st_size / (1024*1024), 1)
        except Exception:
            pass
        try:
            r = _silent_run(
                ["ffprobe","-v","quiet","-print_format","json","-show_format","-show_streams",self.path],
                capture_output=True, text=True, timeout=8
            )
            if r.returncode == 0:
                import json as _j
                data = _j.loads(r.stdout)
                fmt = data.get("format",{})
                self.duration_sec = float(fmt.get("duration",0))
                m,s = divmod(int(self.duration_sec),60)
                self.duration_str = f"{m}:{s:02d}"
                for stream in data.get("streams",[]):
                    if stream.get("codec_type") == "video":
                        try:
                            fps_str = str(stream.get("r_frame_rate","0/1"))
                            num, den = fps_str.split('/')
                            self.fps = round(int(num)/max(1,int(den)), 1)
                        except Exception:
                            self.fps = 0
                        self.width = stream.get("width",0)
                        self.height = stream.get("height",0)
                        self.resolution = f"{self.width}x{self.height}"
                        break
        except Exception:
            pass
        self._probed = True


class DriveScanner:
    def __init__(self):
        self._drives = []; self._cache = {}
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def get_drives(self) -> List[str]:
        if IS_WINDOWS:
            if HAS_WIN32:
                try:
                    drives = win32api.GetLogicalDriveStrings()
                    return [d for d in drives.split('\0') if d and os.path.exists(d)]
                except Exception:
                    pass
            import string
            return [f"{l}:\\" for l in string.ascii_uppercase if os.path.exists(f"{l}:\\")]
        roots = []
        if os.path.exists("/"): roots.append("/")
        home = str(Path.home())
        if os.path.exists(home): roots.append(home)
        return roots

    def scan_drive_root(self, drive_path: str) -> DriveEntry:
        letter = drive_path[0]
        entry = DriveEntry(f"{letter}:", drive_path, is_drive=True)
        try:
            for item in sorted(os.scandir(drive_path), key=lambda e: e.name):
                if not item.is_dir(): continue
                if item.name.startswith('.') or item.name.startswith('$'): continue
                skip = {"Windows","Program Files","Program Files (x86)","ProgramData","Recovery",
                        "AppData","System Volume Information","Config.Msi","Documents and Settings"}
                if item.name in skip: continue
                entry.children.append(DriveEntry(item.name, item.path))
        except PermissionError:
            pass
        return entry

    def scan_folder(self, folder_path: str, max_depth: int = 3, progress: Callable = None) -> DriveEntry:
        name = Path(folder_path).name or folder_path
        entry = DriveEntry(name, folder_path)
        if max_depth <= 0: return entry
        try:
            subdirs = []
            for item in sorted(os.scandir(folder_path), key=lambda e: e.name):
                if item.is_file() and item.name.lower().endswith(tuple(VIDEO_EXT)):
                    entry.video_count += 1
                elif item.is_dir() and not item.name.startswith('.') and not item.name.startswith('$'):
                    subdirs.append(item)
            for item in subdirs:
                child = self.scan_folder(item.path, max_depth - 1)
                if child.video_count > 0:
                    entry.children.append(child)
                    entry.video_count += child.video_count
        except PermissionError:
            pass
        if progress: progress(folder_path, entry.video_count)
        return entry

    def list_videos(self, folder_path: str, recursive: bool = True,
                    probe: bool = False, progress: Callable = None,
                    cancel_event: threading.Event = None) -> List[VideoEntry]:
        """列出视频 — 默认不 probe（延迟加载），可选异步 probe + 进度回调"""
        self._cancel.clear()
        ev = cancel_event or self._cancel
        videos = []
        if recursive:
            for root, dirs, files in os.walk(folder_path):
                if ev.is_set(): break
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for f in sorted(files):
                    if f.lower().endswith(tuple(VIDEO_EXT)):
                        videos.append(VideoEntry(os.path.join(root, f)))
        else:
            for f in sorted(Path(folder_path).iterdir()):
                if f.is_file() and f.suffix.lower() in VIDEO_EXT:
                    videos.append(VideoEntry(str(f)))

        if probe and videos:
            self._batch_probe(videos, progress, ev)
        return videos

    def _batch_probe(self, videos: List[VideoEntry], progress: Callable = None,
                     cancel_event: threading.Event = None):
        """ThreadPoolExecutor 并发 probe — 静默 + 进度回调"""
        ev = cancel_event or self._cancel
        total = len(videos)
        done = [0]

        def _probe_one(ve: VideoEntry):
            if ev.is_set(): return ve
            ve.probe()
            done[0] += 1
            if progress:
                progress(done[0], total, ve)
            return ve

        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = [pool.submit(_probe_one, v) for v in videos]
            for _ in as_completed(futs):
                if ev.is_set(): break

    def get_quick_scan(self) -> List[DriveEntry]:
        results = []
        known = [
            (r"Z:\已处理素材\卖点展示类素材", "Z:卖点展示"),
            (r"Z:\已处理素材\效果展示类素材", "Z:效果展示"),
            (r"Z:\B组更新视频", "Z:B组视频"),
        ]
        for path, label in known:
            if os.path.exists(path):
                entry = DriveEntry(label, path)
                entry.video_count = self._fast_count(path)
                if entry.video_count > 0:
                    results.append(entry)
        for drive in self.get_drives():
            letter = drive[0] if IS_WINDOWS else drive
            if IS_WINDOWS and letter in ('Z','C'): continue
            root = self.scan_drive_root(drive)
            total = sum(self._fast_count(c.path) for c in root.children)
            if total > 0:
                root.video_count = total
                root.name = f"{letter}: ({total}video)"
                results.append(root)
        return results

    def _fast_count(self, path, depth=2):
        c = 0
        try:
            for e in os.scandir(path):
                if e.is_file() and e.name.lower().endswith(tuple(VIDEO_EXT)): c += 1
                elif e.is_dir() and depth > 0 and not e.name.startswith('.'): c += self._fast_count(e.path, depth-1)
        except Exception:
            pass
        return c


# 全局单例
_scanner = None
_scanner_lock = __import__('threading').Lock()
def get_scanner():
    global _scanner
    if _scanner is None:
        with _scanner_lock:
            if _scanner is None:
                _scanner = DriveScanner()
    return _scanner
