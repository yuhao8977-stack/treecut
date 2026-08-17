"""品牌侵权与违规广告检测插件"""
import os
import cv2
import numpy as np
from plugins.base_plugin import BasePlugin
from utils.logging import get_loguru_logger as get_logger
from decord import VideoReader, cpu
from core.model_pool import model_pool
from core.database import execute_sql
from utils.cache_manager import cache_manager
from core.config_loader import CONFIG
logger = get_logger("plugin.brand_detect")
LOGO_DIR = "./data/brand_logos"
os.makedirs(LOGO_DIR, exist_ok=True)
def load_yolo():
    from ultralytics import YOLO
    model_path = "./data/models/yolov8n/yolov8n.pt"
    if os.path.exists(model_path):
        model = YOLO(model_path)
    else:
        model = YOLO("yolov8n.pt")
    model.to("cuda")
    return model
class BrandDetectPlugin(BasePlugin):
    name = "brand_detect"
    category = "quality"
    description = "品牌侵权与违规广告检测"
    def run(self, material_id: int, video_path: str) -> dict:
        cached = cache_manager.get(video_path, "brand_detect")
        if cached:
            for issue in cached:
                execute_sql(
                    "INSERT OR IGNORE INTO quality_results (material_id, check_type, issue_level, issue_desc, start_time, end_time) VALUES (?, ?, ?, ?, ?, ?)",
                    (material_id, "内容合规", issue["level"], issue["desc"], issue["start"], issue["end"])
                )
            return {"status": "cached", "count": len(cached)}
        # 尝试加载YOLO
        yolo_model = None
        try:
            yolo_model = model_pool.get_model("yolov8", load_yolo)
        except Exception as e:
            logger.warning(f"YOLO不可用: {e}，使用ORB特征匹配方案")
        try:
            from decord import gpu
            vr = VideoReader(video_path, ctx=gpu(0), num_threads=CONFIG["performance"]["cpu_threads"])
        except Exception:
            vr = VideoReader(video_path, ctx=cpu(0), num_threads=CONFIG["performance"]["cpu_threads"])
        total_frames = len(vr)
        fps = vr.get_avg_fps()
        step = max(1, int(fps / 1))
        frame_indices = list(range(0, total_frames, step))
        issues = []
        # 模式1: YOLO检测
        if yolo_model is not None:
            for batch_start in range(0, len(frame_indices), 8):
                batch_idx = frame_indices[batch_start:batch_start + 8]
                try:
                    batch_frames = vr.get_batch(batch_idx).asnumpy()
                    results = yolo_model(batch_frames, verbose=False)
                except Exception:
                    continue
                for idx, res in enumerate(results):
                    current_time = batch_idx[idx] / max(fps, 1)
                    if res.boxes is None:
                        continue
                    for box in res.boxes:
                        cls_id = int(box.cls[0]) if hasattr(box.cls, '__getitem__') else int(box.cls)
                        cls_name = res.names.get(cls_id, f"class_{cls_id}")
                        conf = float(box.conf[0]) if hasattr(box.conf, '__getitem__') else float(box.conf)
                        if conf > 0.5 and cls_name.lower() in ["cell phone", "laptop", "tv", "bottle", "book"]:
                            issues.append({
                                "start": round(current_time, 2),
                                "end": round(current_time + 1, 2),
                                "level": "warning",
                                "desc": f"检测到{cls_name}，置信度{conf:.2f}",
                            })
                            execute_sql(
                                "INSERT INTO quality_results (material_id, check_type, issue_level, issue_desc, start_time, end_time) VALUES (?, ?, ?, ?, ?, ?)",
                                (material_id, "内容合规", "warning", f"检测到{cls_name}", current_time, current_time + 1)
                            )
        # 模式2: ORB特征匹配自定义logo库
        else:
            custom_logos = [f for f in os.listdir(LOGO_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
            if custom_logos:
                orb = cv2.ORB_create(nfeatures=1000)
                bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
                logo_features = []
                for logo_file in custom_logos:
                    logo_path = os.path.join(LOGO_DIR, logo_file)
                    logo_img = cv2.imread(logo_path, 0)
                    if logo_img is None:
                        continue
                    kp, des = orb.detectAndCompute(logo_img, None)
                    if des is not None:
                        logo_features.append({"name": logo_file, "kp": kp, "des": des})
                for i in frame_indices:
                    try:
                        frame = vr[i].asnumpy()
                    except Exception:
                        continue
                    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
                    kp_frame, des_frame = orb.detectAndCompute(gray, None)
                    if des_frame is None:
                        continue
                    for logo in logo_features:
                        try:
                            matches = bf.match(logo["des"], des_frame)
                        except Exception:
                            continue
                        good = [m for m in matches if m.distance < 50]
                        if len(good) > 15:
                            current_time = i / max(fps, 1)
                            issues.append({
                                "start": round(current_time, 2),
                                "end": round(current_time + 1, 2),
                                "level": "warning",
                                "desc": f"匹配到品牌特征: {logo['name']}，{len(good)}个匹配点",
                            })
        del vr
        cache_manager.set(video_path, "brand_detect", issues)
        logger.info(f"品牌检测完成，发现{len(issues)}处")
        return {"status": "success", "count": len(issues)}
