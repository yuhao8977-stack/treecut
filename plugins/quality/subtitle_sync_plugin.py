"""音画字幕同步检测插件"""
from plugins.base_plugin import BasePlugin
from utils.logging import get_loguru_logger as get_logger
from core.database import execute_sql, query_sql
from utils.cache_manager import cache_manager
logger = get_logger("plugin.subtitle_sync")
class SubtitleSyncPlugin(BasePlugin):
    name = "subtitle_sync"
    category = "quality"
    description = "音画字幕同步检测"
    def run(self, material_id: int, video_path: str) -> dict:
        cache_key = f"sync_{material_id}"
        cached = cache_manager.get(cache_key, "sync_check")
        if cached:
            for issue in cached:
                execute_sql(
                    "INSERT OR IGNORE INTO quality_results (material_id, check_type, issue_level, issue_desc, start_time, end_time) VALUES (?, ?, ?, ?, ?, ?)",
                    (material_id, "音画同步", "warning", issue["desc"], issue["time"], issue["time"] + 1)
                )
            return {"status": "cached", "count": len(cached)}
        audio_segs = query_sql(
            "SELECT start_time, end_time FROM audio_features WHERE material_id=? AND audio_type='语音' ORDER BY start_time",
            (material_id,)
        )
        sub_segs = query_sql(
            "SELECT start_time, end_time FROM subtitle_features WHERE material_id=? ORDER BY start_time",
            (material_id,)
        )
        if not audio_segs or not sub_segs:
            logger.info("音频或字幕数据不足，跳过同步检测")
            return {"status": "skipped", "count": 0}
        issues = []
        threshold = 0.2
        for a_start, a_end in audio_segs:
            matched = False
            for s_start, s_end in sub_segs:
                if abs(a_start - s_start) < threshold and abs(a_end - s_end) < threshold:
                    matched = True
                    break
            if not matched:
                issues.append({"time": a_start, "desc": "字幕时间轴偏差超过0.2s"})
                execute_sql(
                    "INSERT INTO quality_results (material_id, check_type, issue_level, issue_desc, start_time, end_time) VALUES (?, ?, ?, ?, ?, ?)",
                    (material_id, "音画同步", "warning", "字幕时间轴偏差", a_start, a_end)
                )
        cache_manager.set(cache_key, "sync_check", issues)
        logger.info(f"音画同步检测完成，偏差{len(issues)}处")
        return {"status": "success", "count": len(issues)}
