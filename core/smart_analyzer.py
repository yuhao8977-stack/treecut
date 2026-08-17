"""
树剪 TreeCut v11.3 — 智能视频分析调度器（稳定版）
=================================================
对视频进行全自动帧级分析：
1. 每秒抽取4帧 (可配置)
2. 使用Qwen3-VL-4B检测岛台画面
3. 检测到岛台后写入 video_frames 表
4. 串行处理（一次一个视频），5分钟超时保护
5. 每视频后 gc+torch 内存回收
"""

import os
import re
import gc
import json
import time
import hashlib
import threading
import tempfile
import shutil
from pathlib import Path
from typing import List, Optional, Callable

_PROJ_ROOT = Path(__file__).parent.parent

# 岛台相关关键词
ISLAND_KEYWORDS = [
    "岛台", "中岛", "半岛", "厨房岛台", "岛台台面", "岩板台面",
    "岛头", "餐边柜", "厨房中岛", "台下盆", "台面",
]
_ISLAND_PATTERN = re.compile("|".join(re.escape(kw) for kw in ISLAND_KEYWORDS))

# 跳过目录名（不区分大小写）
SKIP_DIRS = {
    "$recycle.bin", "system volume information", "windows", "program files",
    "program files (x86)", "programdata", "appdata", "temp", "tmp", "__pycache__",
    ".git", "node_modules",
}

# 支持的视频扩展名
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv"}


def _is_island_related(analysis_result: dict) -> bool:
    caption = analysis_result.get("caption", "")
    objects = " ".join(analysis_result.get("objects", []))
    return bool(_ISLAND_PATTERN.search(caption + " " + objects))


def _collect_videos(root_dirs: List[str], max_depth: int = 5, seen_dirs: set = None) -> List[str]:
    """递归收集指定目录下的所有视频文件，跳过系统目录，限制深度，去重。"""
    if seen_dirs is None:
        seen_dirs = set()
    videos = []
    for root_dir in root_dirs:
        rd = os.path.abspath(root_dir)
        if rd in seen_dirs:
            continue
        seen_dirs.add(rd)
        if not os.path.isdir(rd):
            continue
        if max_depth <= 0:
            continue
        try:
            for entry in os.scandir(rd):
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name.lower() in SKIP_DIRS:
                            continue
                        if entry.name.startswith("."):
                            continue
                        videos.extend(_collect_videos([entry.path], max_depth - 1, seen_dirs))
                    elif entry.is_file(follow_symlinks=False):
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in VIDEO_EXTS:
                            videos.append(entry.path)
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            continue
    return videos


class SmartVideoAnalyzer:
    """智能视频分析调度器 — v11.3 串行稳定版"""

    def __init__(self):
        self._vision_model = None
        self._frame_extractor = None
        self._db = None
        self._kb = None
        self._lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # 初始不暂停

        # 统计
        self.total_frames = 0
        self.island_frames = 0
        self.saved_count = 0
        self.videos_scanned = 0

    def cancel(self):
        self._cancel_event.set()
        if not self._pause_event.is_set():
            self._pause_event.set()

    def reset_cancel(self):
        self._cancel_event.clear()
        self._pause_event.set()

    def pause(self):
        self._pause_event.clear()

    def resume(self):
        self._pause_event.set()

    def _lazy_load_vision(self):
        if self._vision_model is None:
            from core.vision_unified import VisionModel
            self._vision_model = VisionModel()

    def _lazy_load_frame_extractor(self):
        if self._frame_extractor is None:
            from core.frame_extractor import FrameExtractor
            self._frame_extractor = FrameExtractor()

    def _lazy_load_db(self):
        if self._db is None:
            from core.database import db
            self._db = db

    def _lazy_load_kb(self):
        if self._kb is None:
            from utils.knowledge import KnowledgeBridge
            self._kb = KnowledgeBridge()

    def _reclaim_memory(self):
        """回收GPU和Python内存"""
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    # ═══════════════════════════════════════════════════
    # 串行批量扫描（稳定核心）
    # ═══════════════════════════════════════════════════

    def scan_videos(
        self,
        root_dirs: List[str],
        frame_interval: float = 0.25,
        timeout_per_video: float = 300.0,
        on_video_start: Callable = None,
        on_video_done: Callable = None,
        on_frame: Callable = None,
        on_progress: Callable = None,
        on_log: Callable = None,
    ) -> dict:
        """
        串行扫描指定目录下的所有视频。

        参数:
            root_dirs: 根目录列表
            frame_interval: 抽帧间隔(秒)
            timeout_per_video: 每个视频的超时时间(秒)
            on_video_start: (video_path, index, total) 回调
            on_video_done: (video_path, result) 回调
            on_frame: (frame_data) 回调
            on_progress: (scanned, total, status) 回调
            on_log: (message) 回调

        返回:
            {"total": int, "scanned": int, "island_total": int, "saved_total": int, "errors": list}
        """
        self.reset_cancel()
        self.videos_scanned = 0

        # 收集视频
        if on_log:
            on_log("正在扫描目录收集视频文件...")
        video_paths = _collect_videos(root_dirs, max_depth=5)
        total = len(video_paths)

        if on_log:
            on_log(f"发现 {total} 个视频文件待分析")
        if on_progress:
            on_progress(0, total, f"0/{total}")

        results = []
        errors = []
        island_total = 0
        saved_total = 0

        for idx, vp in enumerate(video_paths):
            # 检查取消
            if self._cancel_event.is_set():
                if on_log:
                    on_log("扫描已取消")
                break

            # 检查暂停
            while not self._pause_event.is_set():
                if self._cancel_event.is_set():
                    break
                time.sleep(0.3)

            if self._cancel_event.is_set():
                break

            # 视频开始回调
            if on_video_start:
                on_video_start(vp, idx + 1, total)
            if on_log:
                fname = Path(vp).name
                on_log(f"[{idx+1}/{total}] {fname}")
            if on_progress:
                on_progress(idx, total, f"分析: {idx+1}/{total}")

            # 带超时的单视频分析
            result = {"video_path": vp, "error": None, "island_found": 0, "saved": 0}

            def _analyze():
                return self.analyze_video_frames(
                    vp, frame_interval=frame_interval,
                    on_frame_callback=on_frame,
                    log_callback=on_log,
                )

            # 在独立线程中执行（为了超时控制）
            analysis_result = [None]
            analysis_error = [None]
            thread_done = threading.Event()

            def _runner():
                try:
                    analysis_result[0] = _analyze()
                except Exception as e:
                    analysis_error[0] = e
                finally:
                    thread_done.set()

            t = threading.Thread(target=_runner, daemon=True)
            t.start()
            finished = thread_done.wait(timeout=timeout_per_video)

            if not finished:
                # 超时 → 跳过该视频
                self._cancel_event.set()  # 通知内部停止
                t.join(timeout=5)
                self._cancel_event.clear()  # 重置以继续下一个
                result["error"] = f"超时 ({timeout_per_video}s)"
                if on_log:
                    on_log(f"  ⏰ 超时，已跳过")
            elif analysis_error[0]:
                result["error"] = str(analysis_error[0])
                if on_log:
                    on_log(f"  ❌ {analysis_error[0]}")
            else:
                ar = analysis_result[0]
                if ar:
                    result["island_found"] = ar.get("island_frames", 0)
                    result["saved"] = ar.get("saved_frames", 0)
                    result["total_frames"] = ar.get("total_frames", 0)
                    if ar.get("error"):
                        result["error"] = ar["error"]

            island_total += result.get("island_found", 0)
            saved_total += result.get("saved", 0)
            if result.get("error"):
                errors.append({"path": vp, "error": result["error"]})
            results.append(result)
            self.videos_scanned = idx + 1

            if on_video_done:
                on_video_done(vp, result)
            if on_progress:
                on_progress(idx + 1, total,
                           f"✓ {idx+1}/{total} | 岛台:{island_total}")

            # 内存回收
            self._reclaim_memory()
            # 让出CPU
            time.sleep(0.3)

        # 汇总
        summary = {
            "total": total,
            "scanned": self.videos_scanned,
            "island_total": island_total,
            "saved_total": saved_total,
            "errors": errors,
        }

        if on_log:
            on_log(f"扫描完成: {self.videos_scanned}/{total} 个视频, "
                   f"岛台帧: {island_total}, 入库: {saved_total}")

        return summary

    # ═══════════════════════════════════════════════════
    # 帧级分析（单视频）
    # ═══════════════════════════════════════════════════

    def analyze_video_frames(
        self,
        video_path: str,
        frame_interval: float = 0.25,
        output_frames_dir: str = None,
        on_frame_callback: Callable = None,
        log_callback: Callable = None,
    ) -> dict:
        """帧级分析单个视频并写入 video_frames 表。"""
        result = {
            "video_path": video_path,
            "total_frames": 0,
            "island_frames": 0,
            "saved_frames": 0,
            "frames_data": [],
            "error": None,
        }

        try:
            self._lazy_load_vision()
            self._lazy_load_frame_extractor()
            self._lazy_load_db()
            self._lazy_load_kb()

            from core.frame_extractor import get_video_duration
            duration = get_video_duration(video_path)
            if duration <= 0:
                result["error"] = "无法获取时长"
                return result

            video_hash = hashlib.md5(video_path.encode()).hexdigest()[:12]
            if output_frames_dir is None:
                output_frames_dir = str(_PROJ_ROOT / "shipin" / "frames" / video_hash)
            os.makedirs(output_frames_dir, exist_ok=True)
            source_folder = str(Path(video_path).parent)

            tmp_dir = tempfile.mkdtemp(prefix="treecut_frames_")
            try:
                frames = self._frame_extractor.extract_frames_to_files(
                    video_path, interval_sec=frame_interval,
                    output_dir=tmp_dir, include_all=True
                )

                total_frames = len(frames)
                result["total_frames"] = total_frames

                if total_frames == 0:
                    result["error"] = "抽帧失败"
                    return result

                for idx, frame_info in enumerate(frames):
                    if self._cancel_event.is_set():
                        result["error"] = "用户取消"
                        break

                    timestamp = frame_info["timestamp"]
                    tmp_path = frame_info["path"]

                    try:
                        analysis = self._vision_model.analyze(tmp_path)
                        caption = analysis.get("caption", "")
                        objects_str = ", ".join(analysis.get("objects", []))
                        materials_str = ", ".join(analysis.get("materials", []))
                        colors_str = ", ".join(analysis.get("colors", []))
                        style = analysis.get("style", "")
                        scene_type = self._infer_scene_type(caption, objects_str)

                        safe_ts = f"{timestamp:.3f}".replace(".", "_")
                        perm_path = os.path.join(output_frames_dir, f"frame_{safe_ts}s.jpg")
                        shutil.copy2(tmp_path, perm_path)

                        frame_data = {
                            "video_path": video_path,
                            "frame_timestamp": timestamp,
                            "frame_image_path": perm_path,
                            "caption": caption[:500] if caption else "",
                            "objects": objects_str,
                            "materials": materials_str,
                            "colors": colors_str,
                            "style": style,
                            "scene_type": scene_type,
                            "model_confidence": 0.8,
                        }

                        with self._lock:
                            frame_id = self._db.insert_frame(frame_data)

                        result["saved_frames"] += 1
                        frame_data["id"] = frame_id
                        frame_data["is_island"] = _is_island_related(analysis)
                        result["frames_data"].append(frame_data)

                        if frame_data["is_island"]:
                            self.island_frames += 1
                            result["island_frames"] += 1

                            # 岛台帧 → 同步写入 materials 表
                            self._save_to_materials(
                                video_path, timestamp, duration,
                                analysis, objects_str, materials_str,
                                colors_str, style, source_folder
                            )

                        if on_frame_callback:
                            on_frame_callback(frame_data)

                        # 每帧后删除临时文件，释放磁盘
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass

                    except Exception as e:
                        if log_callback:
                            log_callback(f"  ⚠ 帧@{timestamp:.1f}s: {e}")
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass
                        continue

            finally:
                try:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception:
                    pass

            # 标记已分析
            self._mark_analyzed(video_path, duration)

        except Exception as e:
            result["error"] = str(e)
            import traceback
            traceback.print_exc()

        return result

    def _save_to_materials(self, video_path, timestamp, duration,
                           analysis, objects_str, materials_str,
                           colors_str, style, source_folder):
        """将岛台帧同步写入 materials 表"""
        try:
            all_tags = set(analysis.get("objects", []))
            all_tags.update(analysis.get("materials", []))
            db_data = {
                "video_path": video_path,
                "start_time": max(0, timestamp - 1.5),
                "end_time": min(duration, timestamp + 1.5),
                "tags": " ".join(sorted(all_tags)),
                "objects": objects_str,
                "style": style,
                "color": colors_str,
                "material": materials_str,
                "speech_text": "",
                "confidence": 0.8,
                "embedding": None,
                "source_folder": source_folder,
                "duration": duration,
                "file_size": os.path.getsize(video_path),
                "file_mtime": os.path.getmtime(video_path),
            }
            self._db.insert_analysis(db_data, ["qwen3-vl"])
            self.saved_count += 1
        except Exception:
            pass

    def _mark_analyzed(self, video_path: str, duration: float):
        try:
            with self._db.get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO video_registry
                    (video_path, file_mtime, file_size, duration, analyzed, last_checked)
                    VALUES (?,?,?,?,1,CURRENT_TIMESTAMP)
                """, (video_path,
                     os.path.getmtime(video_path),
                     os.path.getsize(video_path),
                     duration))
                conn.execute("""
                    UPDATE materials SET has_frames = 1
                    WHERE video_path = ? AND analyzed = 1
                """, (video_path,))
        except Exception:
            pass
        self._db._notify_changed(video_path)

    def _infer_scene_type(self, caption: str, objects_str: str) -> str:
        combined = (caption + " " + objects_str).lower()
        if any(kw in combined for kw in ["厨房", "岛台", "台面", "水槽"]):
            return "厨房/岛台"
        elif any(kw in combined for kw in ["客厅", "沙发"]):
            return "客厅"
        elif any(kw in combined for kw in ["餐桌", "餐边柜", "吧台"]):
            return "餐厅"
        elif any(kw in combined for kw in ["户外", "花园", "阳台"]):
            return "户外"
        elif any(kw in combined for kw in ["工厂", "车间", "生产"]):
            return "工厂"
        elif any(kw in combined for kw in ["石材", "岩板", "大理石"]):
            return "建材展示"
        return "其他"


# 全局单例
_analyzer_instance = None
_analyzer_lock = threading.Lock()


def get_analyzer() -> SmartVideoAnalyzer:
    global _analyzer_instance
    if _analyzer_instance is None:
        with _analyzer_lock:
            if _analyzer_instance is None:
                _analyzer_instance = SmartVideoAnalyzer()
    return _analyzer_instance
