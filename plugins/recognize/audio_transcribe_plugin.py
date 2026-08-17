"""语音识别与转写插件"""
from plugins.base_plugin import BasePlugin
from utils.logging import get_loguru_logger as get_logger
from core.model_pool import model_pool
from core.database import execute_sql
from utils.cache_manager import cache_manager
from core.config_loader import CONFIG
logger = get_logger("plugin.audio_transcribe")
def load_whisper():
    from faster_whisper import WhisperModel
    model_path = "./data/models/faster-whisper-small"
    return WhisperModel(
        model_path if __import__("os").path.exists(model_path) else "small",
        device="cuda",
        compute_type="int8_float16",
        cpu_threads=CONFIG["performance"]["cpu_threads"],
    )
class AudioTranscribePlugin(BasePlugin):
    name = "audio_transcribe"
    category = "recognize"
    description = "语音识别与转写"
    def run(self, material_id: int, video_path: str) -> dict:
        cached = cache_manager.get(video_path, "audio_transcribe")
        if cached:
            for seg in cached:
                execute_sql(
                    "INSERT OR IGNORE INTO audio_features (material_id, start_time, end_time, audio_type, transcript) VALUES (?, ?, ?, ?, ?)",
                    (material_id, seg["start"], seg["end"], "语音", seg["text"])
                )
            return {"status": "cached", "count": len(cached)}
        try:
            model = model_pool.get_model("faster_whisper", load_whisper)
        except Exception as e:
            logger.warning(f"Whisper模型加载失败: {e}，跳过语音识别")
            return {"status": "failed", "error": str(e)}
        segments, info = model.transcribe(
            video_path,
            language="zh",
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            initial_prompt="家居产品解说，包含岛台、岩板、滑轨、柜体、五金等专业术语",
        )
        segments_list = []
        for seg in segments:
            seg_data = {
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
            }
            segments_list.append(seg_data)
            execute_sql(
                "INSERT INTO audio_features (material_id, start_time, end_time, audio_type, transcript) VALUES (?, ?, ?, ?, ?)",
                (material_id, seg.start, seg.end, "语音", seg.text.strip()),
            )
        cache_manager.set(video_path, "audio_transcribe", segments_list)
        logger.info(f"语音识别完成，共{len(segments_list)}段")
        return {"status": "success", "count": len(segments_list)}
