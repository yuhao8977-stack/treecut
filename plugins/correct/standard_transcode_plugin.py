"""自动转码到标准参数插件"""
import os
import subprocess
from plugins.base_plugin import BasePlugin
from utils.logging import get_loguru_logger as get_logger
from core.database import execute_sql, query_sql
from utils.cache_manager import cache_manager
from core.config_loader import CONFIG
logger = get_logger("plugin.standard_transcode")
OUTPUT_DIR = CONFIG["auto_correct"]["output_dir"]
os.makedirs(OUTPUT_DIR, exist_ok=True)
CFG = CONFIG["auto_correct"]
class StandardTranscodePlugin(BasePlugin):
    name = "standard_transcode"
    category = "correct"
    description = "自动转码到标准参数（分辨率+帧率+码率）"
    def run(self, material_id: int, video_path: str) -> dict:
        param_issues = query_sql(
            "SELECT id FROM quality_results WHERE material_id=? AND check_type='参数合规' AND is_fixed=0",
            (material_id,)
        )
        aspect_issues = query_sql(
            "SELECT id FROM quality_results WHERE material_id=? AND check_type='画幅合规' AND is_fixed=0",
            (material_id,)
        )
        if not param_issues and not aspect_issues:
            return {"status": "skipped", "fixed": 0}
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        output_path = os.path.join(OUTPUT_DIR, f"{base_name}_standard.mp4")
        w, h = 1080, 1920
        vf_filter = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
        )
        # 检测NVENC可用性
        vcodec = "libx264"
        try:
            test = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True, text=True, timeout=10, encoding="utf-8"
            )
            if "h264_nvenc" in test.stdout:
                vcodec = "h264_nvenc"
        except Exception:
            pass
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", vf_filter,
            "-r", str(CFG["standard_fps"]),
            "-b:v", str(CFG["target_bitrate"]),
            "-vcodec", vcodec,
            "-acodec", "aac",
            "-preset", "fast" if vcodec == "libx264" else "p1",
            output_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, encoding="utf-8")
            if result.returncode != 0:
                logger.error(f"标准转码失败: {result.stderr[:300]}")
                return {"status": "failed", "error": result.stderr[:300]}
            execute_sql(
                "UPDATE quality_results SET is_fixed=1 WHERE material_id=? AND check_type IN ('参数合规','画幅合规')",
                (material_id,)
            )
            cache_manager.invalidate(video_path, "param_check")
            cache_manager.invalidate(video_path, "aspect_check")
            execute_sql("UPDATE materials SET file_path=?, version=version+1 WHERE id=?", (output_path, material_id))
            logger.info(f"标准转码完成: {output_path}")
            return {"status": "success", "fixed": len(param_issues) + len(aspect_issues), "output_path": output_path}
        except subprocess.TimeoutExpired:
            return {"status": "failed", "error": "标准转码超时"}
        except Exception as e:
            logger.error(f"标准转码异常: {e}")
            return {"status": "failed", "error": str(e)}
