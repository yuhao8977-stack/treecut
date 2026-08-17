"""黑场/静帧检测插件"""
import cv2
import numpy as np
from plugins.base_plugin import BasePlugin
from utils.logging import get_loguru_logger as get_logger
from decord import VideoReader, cpu
from core.database import execute_sql
from utils.cache_manager import cache_manager
from core.config_loader import CONFIG
logger = get_logger("plugin.black_frame")
class BlackFramePlugin(BasePlugin):
    name = "black_frame"
    category = "quality"
    description = "黑场/静帧检测"
    def run(self, material_id: int, video_path: str) -> dict:
        cached = cache_manager.get(video_path, "black_detect")
        if cached:
            for issue in cached:
                execute_sql(
                    "INSERT OR IGNORE INTO quality_results (material_id, check_type, issue_level, issue_desc, start_time, end_time) VALUES (?, ?, ?, ?, ?, ?)",
                    (material_id, "画面质量", "warning", f"黑场时长{issue['duration']}s", issue["start"], issue["end"])
                )
            return {"status": "cached", "count": len(cached)}
        try:
            from decord import gpu
            vr = VideoReader(video_path, ctx=gpu(0), num_threads=CONFIG["performance"]["cpu_threads"])
        except Exception:
            vr = VideoReader(video_path, ctx=cpu(0), num_threads=CONFIG["performance"]["cpu_threads"])
        total_frames = len(vr)
        fps = vr.get_avg_fps()
        step = max(1, int(fps / CONFIG["sampling"]["base_sample_fps"]))
        issues = []
        in_black = False
        black_start = 0
        threshold = 15
        ratio_threshold = 0.95
        for i in range(0, total_frames, step):
            frame = vr[i].asnumpy()
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            dark_pixels = (gray < threshold).sum()
            dark_ratio = dark_pixels / (gray.shape[0] * gray.shape[1])
            current_time = i / max(fps, 1)
            if dark_ratio > ratio_threshold:
                if not in_black:
                    black_start = current_time
                    in_black = True
            else:
                if in_black:
                    duration = current_time - black_start
                    if duration > 0.5:
                        issues.append({
                            "start": round(black_start, 2),
                            "end": round(current_time, 2),
                            "duration": round(duration, 2),
                        })
                        execute_sql(
                            "INSERT INTO quality_results (material_id, check_type, issue_level, issue_desc, start_time, end_time) VALUES (?, ?, ?, ?, ?, ?)",
                            (material_id, "画面质量", "warning", f"黑场时长{duration:.1f}s", black_start, current_time)
                        )
                    in_black = False
        if in_black:
            duration = (total_frames / max(fps, 1)) - black_start
            if duration > 0.5:
                issues.append({
                    "start": round(black_start, 2),
                    "end": round(total_frames / max(fps, 1), 2),
                    "duration": round(duration, 2),
                })
        del vr
        cache_manager.set(video_path, "black_detect", issues)
        logger.info(f"黑场检测完成，发现{len(issues)}处")
        return {"status": "success", "count": len(issues)}
