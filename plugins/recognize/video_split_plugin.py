"""镜头分割与场景切分插件"""
import os
from plugins.base_plugin import BasePlugin
from utils.logging import get_loguru_logger as get_logger
from utils.ffmpeg_utils import extract_frame, get_video_info
from core.database import execute_sql
from utils.cache_manager import cache_manager
from core.config_loader import CONFIG
logger = get_logger("plugin.video_split")
FEATURE_DIR = "./data/features/scenes"
os.makedirs(FEATURE_DIR, exist_ok=True)
class VideoSplitPlugin(BasePlugin):
    name = "video_split"
    category = "recognize"
    description = "镜头分割与场景切分"
    def run(self, material_id: int, video_path: str) -> dict:
        cached = cache_manager.get(video_path, "scene_split")
        if cached:
            for scene in cached:
                execute_sql(
                    "INSERT OR IGNORE INTO scene_features (material_id, start_time, end_time, keyframe_path) VALUES (?, ?, ?, ?)",
                    (material_id, scene["start"], scene["end"], scene["keyframe"])
                )
            return {"status": "cached", "count": len(cached)}
        logger.info(f"开始镜头分割: {video_path}")
        try:
            from scenedetect import VideoManager, SceneManager
            from scenedetect.detectors import ContentDetector
            threshold = CONFIG["sampling"]["scene_change_threshold"]
            video_manager = VideoManager([video_path])
            scene_manager = SceneManager()
            scene_manager.add_detector(ContentDetector(threshold=threshold))
            video_manager.start()
            scene_manager.detect_scenes(frame_source=video_manager)
            scene_list = scene_manager.get_scene_list()
            video_manager.release()
            scenes = []
            for i, scene in enumerate(scene_list):
                start = scene[0].get_seconds()
                end = scene[1].get_seconds()
                keyframe_path = os.path.join(FEATURE_DIR, f"mat_{material_id}_scene_{i:04d}.jpg")
                extract_frame(video_path, start, keyframe_path)
                execute_sql(
                    "INSERT INTO scene_features (material_id, start_time, end_time, keyframe_path) VALUES (?, ?, ?, ?)",
                    (material_id, start, end, keyframe_path)
                )
                scenes.append({"start": start, "end": end, "keyframe": keyframe_path})
            cache_manager.set(video_path, "scene_split", scenes)
            logger.info(f"镜头分割完成，共{len(scenes)}个场景")
            return {"status": "success", "count": len(scenes)}
        except ImportError:
            # scenedetect不可用时的回退方案：基于采样+帧差
            logger.warning("scenedetect不可用，使用帧差法分割")
            info = get_video_info(video_path)
            fps = info.get("fps", 25)
            duration = info.get("duration", 0)
            if fps == 0:
                return {"status": "failed", "error": "无法获取视频FPS"}
            import cv2
            from decord import VideoReader, cpu
            import numpy as np
            vr = VideoReader(video_path, ctx=cpu(0), num_threads=CONFIG["performance"]["cpu_threads"])
            total_frames = len(vr)
            step = max(1, int(fps / CONFIG["sampling"]["base_sample_fps"]))
            indices = list(range(0, total_frames, step))
            scenes = []
            prev_hist = None
            scene_idx = 0
            threshold = CONFIG["sampling"]["scene_change_threshold"]
            for i, fi in enumerate(indices):
                frame = vr[fi].asnumpy()
                gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
                hist = cv2.calcHist([gray], [0], None, [64], [0, 256])
                hist = cv2.normalize(hist, hist).flatten()
                current_time = fi / fps
                if prev_hist is not None:
                    diff = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CHISQR)
                    if diff > threshold:
                        if scenes:
                            scenes[-1]["end"] = round(current_time, 2)
                        keyframe_path = os.path.join(FEATURE_DIR, f"mat_{material_id}_scene_{scene_idx:04d}.jpg")
                        cv2.imwrite(keyframe_path, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
                        scenes.append({
                            "start": round(current_time, 2),
                            "end": round(min(current_time + 5, duration), 2),
                            "keyframe": keyframe_path,
                        })
                        scene_idx += 1
                if prev_hist is None:
                    keyframe_path = os.path.join(FEATURE_DIR, f"mat_{material_id}_scene_{scene_idx:04d}.jpg")
                    cv2.imwrite(keyframe_path, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
                    scenes.append({"start": 0, "end": round(min(5, duration), 2), "keyframe": keyframe_path})
                prev_hist = hist
            if scenes:
                scenes[-1]["end"] = round(duration, 2)
            del vr
            for scene in scenes:
                execute_sql(
                    "INSERT INTO scene_features (material_id, start_time, end_time, keyframe_path) VALUES (?, ?, ?, ?)",
                    (material_id, scene["start"], scene["end"], scene["keyframe"])
                )
            cache_manager.set(video_path, "scene_split", scenes)
            logger.info(f"帧差法分割完成，共{len(scenes)}个场景")
            return {"status": "success", "count": len(scenes)}
