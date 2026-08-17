"""视频参数合规检测插件"""
from plugins.base_plugin import BasePlugin
from utils.logging import get_loguru_logger as get_logger
from utils.ffmpeg_utils import get_video_info
from core.database import execute_sql
from utils.cache_manager import cache_manager
from core.config_loader import CONFIG
logger = get_logger("plugin.param_check")
STANDARD = {"resolution": "1080x1920", "fps": 30, "min_bitrate": 2000000}
class ParamCheckPlugin(BasePlugin):
    name = "param_check"
    category = "quality"
    description = "视频参数合规检测"
    def run(self, material_id: int, video_path: str) -> dict:
        cached = cache_manager.get(video_path, "param_check")
        if cached:
            for issue in cached:
                execute_sql(
                    "INSERT OR IGNORE INTO quality_results (material_id, check_type, issue_level, issue_desc, start_time, end_time) VALUES (?, ?, ?, ?, 0, ?)",
                    (material_id, "参数合规", "error", issue["desc"], issue.get("duration", 0))
                )
            return {"status": "cached", "count": len(cached)}
        info = get_video_info(video_path)
        if not info:
            return {"status": "failed", "error": "无法获取视频信息"}
        issues = []
        if info["resolution"] != STANDARD["resolution"]:
            desc = f"分辨率{info['resolution']}，要求{STANDARD['resolution']}"
            issues.append({"desc": desc, "duration": info["duration"]})
            execute_sql(
                "INSERT INTO quality_results (material_id, check_type, issue_level, issue_desc, start_time, end_time) VALUES (?, ?, ?, ?, 0, ?)",
                (material_id, "参数合规", "error", desc, info["duration"])
            )
        if abs(info["fps"] - STANDARD["fps"]) > 1:
            desc = f"帧率{info['fps']:.1f}，要求{STANDARD['fps']}"
            issues.append({"desc": desc, "duration": info["duration"]})
            execute_sql(
                "INSERT INTO quality_results (material_id, check_type, issue_level, issue_desc, start_time, end_time) VALUES (?, ?, ?, ?, 0, ?)",
                (material_id, "参数合规", "error", desc, info["duration"])
            )
        if info["bitrate"] > 0 and info["bitrate"] < STANDARD["min_bitrate"]:
            desc = f"码率{info['bitrate']}bps，最低要求{STANDARD['min_bitrate']}bps"
            issues.append({"desc": desc, "duration": info["duration"]})
            execute_sql(
                "INSERT INTO quality_results (material_id, check_type, issue_level, issue_desc, start_time, end_time) VALUES (?, ?, ?, ?, 0, ?)",
                (material_id, "参数合规", "error", desc, info["duration"])
            )
        cache_manager.set(video_path, "param_check", issues)
        logger.info(f"参数检测完成，发现{len(issues)}处异常")
        return {"status": "success", "count": len(issues)}
