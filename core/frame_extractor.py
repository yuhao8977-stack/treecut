"""
树剪 AI素材库 — 统一抽帧引擎
支持: 按秒抽帧 / 按场景切换点抽帧 / 关键帧检测
"""
import os, tempfile, shutil
from pathlib import Path
from utils.silent_subprocess import run as _silent_run
from typing import List, Optional, Tuple
from dataclasses import dataclass


# ═══════════════════════════════════════════
# 公共工具函数 (消除三重 _get_duration 重复)
# ═══════════════════════════════════════════

def get_video_duration(path: str) -> float:
    """获取视频时长 (秒) — 所有模块共用"""
    try:
        probe = _silent_run([
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "csv=p=0", path
        ], capture_output=True, text=True, timeout=10)
        return float(probe.stdout.strip() or 0)
    except Exception:
        return 0

@dataclass
class FrameInfo:
    path: str
    time_sec: float
    scene_index: int = -1  # -1=按秒抽帧, >=0=场景检测结果


class FrameExtractor:
    """视频抽帧 — OpenCV主 + FFmpeg备用"""

    def __init__(self, use_gpu: bool = False):
        self.use_gpu = use_gpu
        self._cv2 = None
        try:
            import cv2
            self._cv2 = cv2
        except ImportError:
            pass

    def extract_by_interval(self, video_path: str, interval_sec: float = 1.0,
                            max_frames: int = 60, output_dir: str = None) -> List[FrameInfo]:
        """
        按固定间隔抽帧 (每秒N帧)。
        返回 FrameInfo 列表，包含临时文件路径。
        """
        cleanup = output_dir is None
        if output_dir is None:
            output_dir = tempfile.mkdtemp(prefix="frames_")

        frames = []
        duration = self._get_duration(video_path)
        if duration <= 0:
            return frames

        if self._cv2:
            frames = self._extract_cv2(video_path, interval_sec, max_frames, output_dir, duration)
        else:
            frames = self._extract_ffmpeg(video_path, interval_sec, max_frames, output_dir, duration)

        return frames

    def extract_by_scenes(self, video_path: str, scenes: List[Tuple[float, float]],
                          output_dir: str = None) -> List[FrameInfo]:
        """
        按场景切换点抽帧 — 每个场景取中间帧。
        scenes: [(start_sec, end_sec), ...]
        """
        if output_dir is None:
            output_dir = tempfile.mkdtemp(prefix="scene_frames_")

        frames = []
        for i, (start, end) in enumerate(scenes):
            mid = (start + end) / 2
            out_path = Path(output_dir) / f"scene_{i:04d}_{mid:.1f}s.jpg"
            self._save_frame_at(video_path, mid, str(out_path))
            if out_path.exists():
                frames.append(FrameInfo(path=str(out_path), time_sec=mid, scene_index=i))

        return frames

    def _extract_cv2(self, video_path: str, interval: float, max_frames: int,
                     output_dir: str, duration: float) -> List[FrameInfo]:
        frames = []
        cap = self._cv2.VideoCapture(video_path)
        # v12.0: 验证视频是否成功打开
        if not cap.isOpened():
            cap.release()
            return self._extract_ffmpeg(video_path, interval, max_frames, output_dir, duration)
        fps = cap.get(self._cv2.CAP_PROP_FPS)
        if fps <= 0:
            cap.release()
            return self._extract_ffmpeg(video_path, interval, max_frames, output_dir, duration)
        frame_interval = max(1, int(fps * interval))

        for i in range(0, min(max_frames * frame_interval, int(duration * fps)), frame_interval):
            cap.set(self._cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if not ret:
                break
            time_sec = i / fps
            out_path = Path(output_dir) / f"frame_{time_sec:.1f}s.jpg"
            self._cv2.imwrite(str(out_path), frame, [self._cv2.IMWRITE_JPEG_QUALITY, 85])
            frames.append(FrameInfo(path=str(out_path), time_sec=round(time_sec, 1)))

        cap.release()
        return frames

    def _extract_ffmpeg(self, video_path: str, interval: float, max_frames: int,
                        output_dir: str, duration: float) -> List[FrameInfo]:
        """v12.0 修复: 单次FFmpeg进程批量提取，替代每帧独立进程"""
        frames = []
        fps_val = 1.0 / interval if interval > 0 else 1.0
        pattern = os.path.join(output_dir, "frame_%06d.jpg")
        try:
            _silent_run([
                "ffmpeg", "-y", "-i", video_path,
                "-vf", f"fps={fps_val:.4f}",
                "-frames:v", str(max_frames),
                "-q:v", "2", pattern
            ], capture_output=True, timeout=120)
            import glob as _glob
            for idx, fpath in enumerate(sorted(_glob.glob(os.path.join(output_dir, "frame_*.jpg")))):
                t = round(idx * interval, 1)
                if t <= duration:
                    frames.append(FrameInfo(path=fpath, time_sec=t))
        except Exception:
            pass  # 回退: 返回空列表，调用方检查 _cv2 可用性
        return frames

    def _save_frame_at(self, video_path: str, time_sec: float, output_path: str):
        if self._cv2:
            cap = self._cv2.VideoCapture(video_path)
            fps = cap.get(self._cv2.CAP_PROP_FPS)
            cap.set(self._cv2.CAP_PROP_POS_FRAMES, int(time_sec * fps))
            ret, frame = cap.read()
            if ret:
                self._cv2.imwrite(output_path, frame, [self._cv2.IMWRITE_JPEG_QUALITY, 85])
            cap.release()
        else:
            _silent_run([
                "ffmpeg", "-y", "-ss", str(time_sec), "-i", video_path,
                "-vframes", "1", "-q:v", "2", output_path
            ], capture_output=True, timeout=10)

    def _get_duration(self, path: str) -> float:
        return get_video_duration(path)

    def cleanup(self, frame_dir: str):
        """清理抽帧临时文件"""
        if os.path.exists(frame_dir):
            shutil.rmtree(frame_dir, ignore_errors=True)

    # ═══════════════════════════════════════════════
    # v11.3: 帧级别提取 — 直接返回文件路径+时间戳字典
    # ═══════════════════════════════════════════════

    def extract_frames_to_files(
        self, video_path: str, interval_sec: float = 0.25,
        output_dir: str = None, max_frames: int = 0,
        include_all: bool = False
    ) -> List[dict]:
        """
        按固定间隔抽取视频帧并保存为文件。

        参数:
            video_path: 视频文件路径
            interval_sec: 抽帧间隔(秒), 默认0.25=每秒4帧
            output_dir: 输出目录。None则创建临时目录。
            max_frames: 最大帧数。0=不限制。
            include_all: True=抽取所有帧(无视max_frames)。用于完整分析。

        返回:
            [{"timestamp": float, "path": str}, ...] — 时间戳(秒)和帧文件路径
        """
        if output_dir is None:
            output_dir = tempfile.mkdtemp(prefix="frames_")

        frames = []
        duration = self._get_duration(video_path)
        if duration <= 0:
            return frames

        max_possible = int(duration / interval_sec) + 1
        if max_frames <= 0:
            max_frames = max_possible

        if self._cv2:
            frames = self._extract_to_files_cv2(
                video_path, interval_sec, min(max_frames, max_possible),
                output_dir, duration
            )
        else:
            frames = self._extract_to_files_ffmpeg(
                video_path, interval_sec, min(max_frames, max_possible),
                output_dir, duration
            )

        return frames

    def _extract_to_files_cv2(
        self, video_path: str, interval: float, max_frames: int,
        output_dir: str, duration: float
    ) -> List[dict]:
        """OpenCV实现: 按间隔跳帧提取"""
        frames = []
        cap = self._cv2.VideoCapture(video_path)
        fps = cap.get(self._cv2.CAP_PROP_FPS)
        if fps <= 0:
            cap.release()
            return frames
        frame_interval_frames = max(1, int(fps * interval))

        frame_idx = 0
        extracted = 0
        while extracted < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % frame_interval_frames == 0:
                timestamp = frame_idx / fps
                if timestamp > duration:
                    break
                out_path = os.path.join(output_dir, f"frame_{timestamp:.3f}s.jpg")
                self._cv2.imwrite(str(out_path), frame,
                                  [self._cv2.IMWRITE_JPEG_QUALITY, 85])
                frames.append({"timestamp": round(timestamp, 3), "path": str(out_path)})
                extracted += 1
            frame_idx += 1

        cap.release()
        return frames

    def _extract_to_files_ffmpeg(
        self, video_path: str, interval: float, max_frames: int,
        output_dir: str, duration: float
    ) -> List[dict]:
        """FFmpeg实现: 使用select滤镜抽帧"""
        frames = []
        # ffmpeg -i input -vf "fps=4" output_%04d.jpg
        fps_val = 1.0 / interval
        pattern = os.path.join(output_dir, "frame_%06d.jpg")

        try:
            from utils.silent_subprocess import run as _silent_run
            _silent_run([
                "ffmpeg", "-y", "-i", video_path,
                "-vf", f"fps={fps_val:.4f}",
                "-frames:v", str(max_frames),
                "-q:v", "2", pattern
            ], capture_output=True, timeout=120)

            # 收集生成的文件
            import glob as _glob
            generated = sorted(_glob.glob(os.path.join(output_dir, "frame_*.jpg")))
            for idx, fpath in enumerate(generated):
                # 从帧号推算时间戳
                timestamp = round(idx / fps_val, 3)
                if timestamp > duration:
                    break
                # 重命名为时间戳格式
                new_name = os.path.join(output_dir, f"frame_{timestamp:.3f}s.jpg")
                try:
                    os.rename(fpath, new_name)
                    frames.append({"timestamp": timestamp, "path": new_name})
                except Exception:
                    frames.append({"timestamp": timestamp, "path": fpath})
        except Exception:
            pass

        return frames
