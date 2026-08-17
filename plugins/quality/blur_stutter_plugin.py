"""画面模糊与卡顿检测插件"""
import cv2
from plugins.base_plugin import BasePlugin
from utils.logging import get_loguru_logger as get_logger
from decord import VideoReader, cpu
from core.database import execute_sql
from utils.cache_manager import cache_manager
from core.config_loader import CONFIG
logger = get_logger("plugin.blur_stutter")
class BlurStutterPlugin(BasePlugin):
    name = "blur_stutter"
    category = "quality"
    description = "画面模糊与卡顿检测"
    def run(self, material_id: int, video_path: str) -> dict:
        cached = cache_manager.get(video_path, "blur_stutter")
        if cached:
            for issue in cached:
                execute_sql(
                    "INSERT OR IGNORE INTO quality_results (material_id, check_type, issue_level, issue_desc, start_time, end_time) VALUES (?, ?, ?, ?, ?, ?)",
                    (material_id, "画面质量", issue["level"], issue["desc"], issue["start"], issue["end"])
                )
            return {"status": "cached", "count": len(cached)}
        try:
            from decord import gpu
            vr = VideoReader(video_path, ctx=gpu(0), num_threads=CONFIG["performance"]["cpu_threads"])
        except Exception:
            vr = VideoReader(video_path, ctx=cpu(0), num_threads=CONFIG["performance"]["cpu_threads"])
        total_frames = len(vr)
        fps = vr.get_avg_fps()
        step = max(1, int(fps / 2))
        frame_indices = list(range(0, total_frames, step))
        issues = []
        prev_gray = None
        blur_thresh = CONFIG["advanced_quality"]["blur_threshold"]
        stutter_thresh = CONFIG["advanced_quality"]["stutter_threshold"]
        for batch_start in range(0, len(frame_indices), 16):
            batch_idx = frame_indices[batch_start:batch_start + 16]
            try:
                batch_frames = vr.get_batch(batch_idx).asnumpy()
            except Exception:
                continue
            for idx, frame in enumerate(batch_frames):
                frame_num = batch_idx[idx]
                current_time = frame_num / max(fps, 1)
                gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
                blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
                if blur_score < blur_thresh:
                    issues.append({
                        "start": round(current_time, 2),
                        "end": round(current_time + 0.5, 2),
                        "level": "warning",
                        "desc": f"画面模糊，清晰度评分{blur_score:.1f}",
                    })
                    execute_sql(
                        "INSERT INTO quality_results (material_id, check_type, issue_level, issue_desc, start_time, end_time) VALUES (?, ?, ?, ?, ?, ?)",
                        (material_id, "画面质量", "warning", f"画面模糊，评分{blur_score:.1f}", current_time, current_time + 0.5)
                    )
                if prev_gray is not None:
                    diff = cv2.absdiff(gray, prev_gray).mean()
                    if diff < stutter_thresh:
                        issues.append({
                            "start": round(current_time - 0.5, 2),
                            "end": round(current_time, 2),
                            "level": "warning",
                            "desc": "帧间变化过低，疑似卡顿",
                        })
                        execute_sql(
                            "INSERT INTO quality_results (material_id, check_type, issue_level, issue_desc, start_time, end_time) VALUES (?, ?, ?, ?, ?, ?)",
                            (material_id, "画面质量", "warning", "帧间变化过低，疑似卡顿", current_time - 0.5, current_time)
                        )
                prev_gray = gray
        del vr
        cache_manager.set(video_path, "blur_stutter", issues)
        logger.info(f"画面质量检测完成，发现{len(issues)}处")
        return {"status": "success", "count": len(issues)}
