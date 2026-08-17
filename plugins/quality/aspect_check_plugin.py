"""画幅比例与黑边检测插件"""
import cv2
import numpy as np
from plugins.base_plugin import BasePlugin
from utils.logging import get_loguru_logger as get_logger
from decord import VideoReader, cpu
from utils.ffmpeg_utils import get_video_info
from core.database import execute_sql
from utils.cache_manager import cache_manager
logger = get_logger("plugin.aspect_check")
STANDARD_RATIO = 9 / 16
class AspectCheckPlugin(BasePlugin):
    name = "aspect_check"
    category = "quality"
    description = "画幅比例与黑边检测"
    def run(self, material_id: int, video_path: str) -> dict:
        cached = cache_manager.get(video_path, "aspect_check")
        if cached:
            for issue in cached:
                execute_sql(
                    "INSERT OR IGNORE INTO quality_results (material_id, check_type, issue_level, issue_desc, start_time, end_time) VALUES (?, ?, ?, ?, 0, ?)",
                    (material_id, "画幅合规", issue["level"], issue["desc"], issue["duration"])
                )
            return {"status": "cached", "count": len(cached)}
        info = get_video_info(video_path)
        if not info:
            return {"status": "failed", "error": "无法获取视频信息"}
        w, h = info["width"], info["height"]
        duration = info["duration"]
        issues = []
        if w > 0 and h > 0:
            actual_ratio = h / w if h < w else w / h
            diff = abs(actual_ratio - STANDARD_RATIO) / STANDARD_RATIO
            if diff > 0.05:
                issues.append({"level": "error", "desc": f"画幅比例不符，实际{w}x{h}，标准9:16", "duration": duration})
                execute_sql(
                    "INSERT INTO quality_results (material_id, check_type, issue_level, issue_desc, start_time, end_time) VALUES (?, ?, ?, ?, 0, ?)",
                    (material_id, "画幅合规", "error", f"画幅比例不符{w}x{h}", duration)
                )
        # 黑边检测
        try:
            try:
                from decord import gpu
                vr = VideoReader(video_path, ctx=gpu(0))
            except Exception:
                vr = VideoReader(video_path, ctx=cpu(0))
            mid_frame = vr[len(vr) // 2].asnumpy()
            gray = cv2.cvtColor(mid_frame, cv2.COLOR_RGB2GRAY)
            del vr
            edge_thresh = 20
            if gray.shape[1] > 20 and gray.shape[0] > 20:
                left_black = np.mean(gray[:, :20]) < edge_thresh
                right_black = np.mean(gray[:, -20:]) < edge_thresh
                top_black = np.mean(gray[:20, :]) < edge_thresh
                bottom_black = np.mean(gray[-20:, :]) < edge_thresh
                if left_black and right_black:
                    issues.append({"level": "warning", "desc": "两侧黑边", "duration": duration})
                if top_black and bottom_black:
                    issues.append({"level": "warning", "desc": "上下黑边", "duration": duration})
        except Exception as e:
            logger.debug(f"黑边检测异常: {e}")
        cache_manager.set(video_path, "aspect_check", issues)
        logger.info(f"画幅检测完成，发现{len(issues)}处")
        return {"status": "success", "count": len(issues)}
