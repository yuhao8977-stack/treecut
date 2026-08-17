"""自动对齐字幕时间轴插件"""
from plugins.base_plugin import BasePlugin
from utils.logging import get_loguru_logger as get_logger
from core.database import execute_sql, query_sql
from utils.cache_manager import cache_manager
logger = get_logger("plugin.subtitle_align")
class SubtitleAlignPlugin(BasePlugin):
    name = "subtitle_align"
    category = "correct"
    description = "自动对齐字幕时间轴匹配语音"
    def run(self, material_id: int, video_path: str) -> dict:
        issues = query_sql(
            "SELECT id FROM quality_results WHERE material_id=? AND check_type='音画同步' AND is_fixed=0",
            (material_id,)
        )
        if not issues:
            return {"status": "skipped", "fixed": 0}
        audio_segs = query_sql(
            "SELECT start_time, end_time FROM audio_features WHERE material_id=? AND audio_type='语音' ORDER BY start_time",
            (material_id,)
        )
        sub_segs = query_sql(
            "SELECT id FROM subtitle_features WHERE material_id=? ORDER BY start_time",
            (material_id,)
        )
        if not audio_segs or not sub_segs:
            return {"status": "skipped", "fixed": 0}
        align_count = min(len(audio_segs), len(sub_segs))
        for i in range(align_count):
            sub_id = sub_segs[i][0]
            execute_sql(
                "UPDATE subtitle_features SET start_time=?, end_time=? WHERE id=?",
                (audio_segs[i][0], audio_segs[i][1], sub_id)
            )
        execute_sql(
            "UPDATE quality_results SET is_fixed=1 WHERE material_id=? AND check_type='音画同步'",
            (material_id,)
        )
        cache_manager.invalidate(f"sync_{material_id}", "sync_check")
        logger.info(f"字幕对齐完成，修正{align_count}条")
        return {"status": "success", "fixed": align_count}
