"""画面字幕OCR识别与纠错插件"""
from plugins.base_plugin import BasePlugin
from utils.logging import get_loguru_logger as get_logger
from core.model_pool import model_pool
from core.database import execute_sql
from utils.cache_manager import cache_manager
from core.config_loader import CONFIG
logger = get_logger("plugin.subtitle_ocr")
def load_rapidocr():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()
class SubtitleOcrPlugin(BasePlugin):
    name = "subtitle_ocr"
    category = "recognize"
    description = "画面字幕OCR识别与纠错"
    def run(self, material_id: int, video_path: str) -> dict:
        cached = cache_manager.get(video_path, "subtitle_detect")
        if cached:
            for sub in cached:
                execute_sql(
                    "INSERT OR IGNORE INTO subtitle_features (material_id, start_time, end_time, content, is_error) VALUES (?, ?, ?, ?, ?)",
                    (material_id, sub["start"], sub["end"], sub["content"], sub.get("has_error", 0))
                )
            return {"status": "cached", "count": len(cached)}
        try:
            ocr = model_pool.get_model("rapid_ocr", load_rapidocr)
        except Exception as e:
            logger.warning(f"RapidOCR加载失败: {e}，跳过字幕识别")
            return {"status": "failed", "error": str(e)}
        # 使用decord解码（自动降级CPU）
        try:
            from decord import VideoReader, gpu
            vr = VideoReader(video_path, ctx=gpu(0), num_threads=CONFIG["performance"]["cpu_threads"])
        except Exception:
            from decord import VideoReader, cpu
            vr = VideoReader(video_path, ctx=cpu(0), num_threads=CONFIG["performance"]["cpu_threads"])
        total_frames = len(vr)
        fps = vr.get_avg_fps()
        frame_step = max(1, int(fps / CONFIG["sampling"]["base_sample_fps"]))
        frame_indices = list(range(0, total_frames, frame_step))
        subtitles = []
        current_text = ""
        start_time = 0
        subtitle_region_ratio = 0.65
        for i in frame_indices:
            frame = vr[i].asnumpy()
            current_time = i / fps
            # 裁切字幕区域（画面下方35%）
            h, w = frame.shape[:2]
            roi_top = int(h * subtitle_region_ratio)
            roi = frame[roi_top:, :, :]
            result, _ = ocr(roi)
            text = "".join([line[1] for line in result]) if result else ""
            if text != current_text:
                if current_text and len(current_text.strip()) > 1:
                    subtitles.append({
                        "start": round(start_time, 2),
                        "end": round(current_time, 2),
                        "content": current_text.strip(),
                    })
                current_text = text
                start_time = current_time
        if current_text and len(current_text.strip()) > 1:
            subtitles.append({
                "start": round(start_time, 2),
                "end": round(total_frames / max(fps, 1), 2),
                "content": current_text.strip(),
            })
        del vr
        # 尝试pycorrector纠错
        corrector = None
        try:
            import pycorrector
            pycorrector.set_custom_word_freq({"岛台": 1000, "岩板": 1000, "滑轨": 1000, "柜体": 1000})
            corrector = pycorrector
        except ImportError:
            logger.debug("pycorrector不可用，跳过文本纠错")
        for sub in subtitles:
            has_error = 0
            corrected_text = sub["content"]
            if corrector:
                try:
                    corrected, detail = corrector.correct(sub["content"])
                    has_error = 1 if len(detail) > 0 else 0
                    corrected_text = corrected
                except Exception:
                    pass
            execute_sql(
                "INSERT INTO subtitle_features (material_id, start_time, end_time, content, is_error) VALUES (?, ?, ?, ?, ?)",
                (material_id, sub["start"], sub["end"], corrected_text, has_error)
            )
            if has_error:
                execute_sql(
                    "INSERT INTO quality_results (material_id, check_type, issue_level, issue_desc, start_time, end_time) VALUES (?, ?, ?, ?, ?, ?)",
                    (material_id, "字幕质量", "warning", f"字幕可能有误: {sub['content'][:30]}...", sub["start"], sub["end"])
                )
        cache_manager.set(video_path, "subtitle_detect", subtitles)
        error_count = sum(1 for s in subtitles if s.get("has_error"))
        logger.info(f"字幕识别完成，共{len(subtitles)}条，疑似错误{error_count}处")
        return {"status": "success", "count": len(subtitles), "errors": error_count}
