"""自动裁剪黑场插件"""
import os
import subprocess
from plugins.base_plugin import BasePlugin
from utils.logging import get_loguru_logger as get_logger
from utils.ffmpeg_utils import get_video_info
from core.database import execute_sql, query_sql
from utils.cache_manager import cache_manager
from core.config_loader import CONFIG
logger = get_logger("plugin.trim_black")
OUTPUT_DIR = CONFIG["auto_correct"]["output_dir"]
os.makedirs(OUTPUT_DIR, exist_ok=True)
class TrimBlackPlugin(BasePlugin):
    name = "trim_black"
    category = "correct"
    description = "自动裁剪黑场片段"
    def run(self, material_id: int, video_path: str) -> dict:
        issues = query_sql(
            """SELECT id, start_time, end_time FROM quality_results
               WHERE material_id=? AND check_type='画面质量'
               AND (issue_desc LIKE '%黑场%' OR issue_desc LIKE '%空白帧%' OR issue_desc LIKE '%亮度过低%')
               AND is_fixed=0""",
            (material_id,)
        )
        if not issues:
            return {"status": "skipped", "fixed": 0}
        logger.info(f"开始自动裁剪黑场，共{len(issues)}处")
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        output_path = os.path.join(OUTPUT_DIR, f"{base_name}_trim_black.mp4")
        info = get_video_info(video_path)
        duration = info.get("duration", 0)
        if duration == 0:
            return {"status": "failed", "error": "无法获取视频时长"}
        # 计算保留片段
        issues_sorted = sorted(issues, key=lambda x: x[1])
        keep_segments = []
        last_end = 0.0
        for issue in issues_sorted:
            _, start, end = issue
            if start > last_end + 0.1:
                keep_segments.append((last_end, start))
            last_end = max(last_end, end)
        if last_end < duration - 0.1:
            keep_segments.append((last_end, duration))
        if not keep_segments:
            return {"status": "skipped", "fixed": 0}
        try:
            if len(keep_segments) == 1:
                start, end = keep_segments[0]
                cmd = ["ffmpeg", "-y", "-ss", str(start), "-to", str(end), "-i", video_path, "-c", "copy", output_path]
            else:
                # 使用concat protocol
                concat_file = os.path.join(OUTPUT_DIR, f"_concat_{material_id}.txt")
                with open(concat_file, "w", encoding="utf-8") as f:
                    for start, end in keep_segments:
                        f.write(f"file '{os.path.abspath(video_path)}'\n")
                        f.write(f"inpoint {start}\n")
                        f.write(f"outpoint {end}\n")
                cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", output_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, encoding="utf-8")
            if result.returncode != 0:
                logger.error(f"黑场裁剪FFmpeg失败: {result.stderr[:200]}")
                return {"status": "failed", "error": result.stderr[:200]}
            # 标记已修复
            for issue in issues_sorted:
                execute_sql("UPDATE quality_results SET is_fixed=1 WHERE id=?", (issue[0],))
            cache_manager.invalidate(video_path, "black_detect")
            execute_sql("UPDATE materials SET file_path=?, version=version+1 WHERE id=?", (output_path, material_id))
            logger.info(f"黑场裁剪完成，修复{len(issues)}处，输出: {output_path}")
            return {"status": "success", "fixed": len(issues), "output_path": output_path}
        except subprocess.TimeoutExpired:
            return {"status": "failed", "error": "黑场裁剪超时"}
        except Exception as e:
            logger.error(f"黑场裁剪异常: {e}")
            return {"status": "failed", "error": str(e)}
