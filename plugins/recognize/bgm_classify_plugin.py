"""BGM风格分类插件"""
import os
import numpy as np
from plugins.base_plugin import BasePlugin
from utils.logging import get_loguru_logger as get_logger
from core.database import execute_sql
from utils.cache_manager import cache_manager
logger = get_logger("plugin.bgm_classify")
STYLES = ["轻快活泼", "舒缓治愈", "动感节奏", "大气震撼", "温馨日常", "科技感"]
class BgmClassifyPlugin(BasePlugin):
    name = "bgm_classify"
    category = "recognize"
    description = "BGM风格分类与节拍检测"
    def run(self, material_id: int, video_path: str) -> dict:
        cached = cache_manager.get(video_path, "bgm_classify")
        if cached:
            execute_sql(
                "INSERT OR IGNORE INTO audio_features (material_id, start_time, end_time, audio_type, transcript) VALUES (?, 0, ?, 'BGM', ?)",
                (material_id, cached["duration"], cached["style"])
            )
            return {"status": "cached", "style": cached["style"]}
        try:
            import tensorflow as tf
            import tensorflow_hub as hub
            import librosa
            # 强制CPU，零显存
            os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
            tf.config.set_visible_devices([], "GPU")
            model_path = "./data/models/yamnet"
            if os.path.exists(model_path):
                model = hub.load(model_path)
            else:
                model = hub.load("https://tfhub.dev/google/yamnet/1")
            wav, sr = librosa.load(video_path, sr=16000, mono=True)
            duration = len(wav) / sr
            if duration < 1.0:
                return {"status": "skipped", "style": "音频过短"}
            scores, _, _ = model(wav)
            class_scores = scores.numpy().mean(axis=0)
            top_idx = int(np.argmax(class_scores))
            style = STYLES[top_idx % len(STYLES)]
            # 节拍检测
            tempo = 0.0
            try:
                tempo_val, _ = librosa.beat.beat_track(y=wav, sr=sr)
                tempo = float(tempo_val)
            except Exception:
                pass
            result = {
                "style": style,
                "tempo": tempo,
                "duration": round(duration, 2),
                "confidence": round(float(class_scores[top_idx]), 4),
            }
            execute_sql(
                "INSERT INTO audio_features (material_id, start_time, end_time, audio_type, transcript) VALUES (?, 0, ?, 'BGM', ?)",
                (material_id, duration, style)
            )
            cache_manager.set(video_path, "bgm_classify", result)
            logger.info(f"BGM分类完成: {style} | 节拍: {tempo:.0f}BPM")
            return {"status": "success", "style": style, "tempo": tempo}
        except ImportError as e:
            logger.warning(f"TensorFlow/librosa不可用: {e}，BGM分类跳过")
            return {"status": "failed", "error": str(e)}
        except Exception as e:
            logger.error(f"BGM分类失败: {e}")
            return {"status": "failed", "error": str(e)}
