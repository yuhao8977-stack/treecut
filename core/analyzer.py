"""
树剪 AI素材库 — 视频分析调度器
四模型并行 + 汇总 → 标签生成 → 入库
"""
import os, time, sqlite3, threading
from pathlib import Path
from typing import Optional, Callable, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.frame_extractor import FrameExtractor, FrameInfo
from core.vision_unified import VisionModel  # 统一视觉模型 (替代旧 QwenVL/CLIP/YOLO)
from core.audio_models import WhisperModel, AudioClassifier, AudioResult
from core.tag_merger import TagMerger



def _detect_human_in_tags(tags: str, objects: str, video_path: str) -> int:
    """Return 1 if the material contains human figures, 0 otherwise."""
    human_kw = ["human","person","people","face","portrait","body","man","woman",
                "人像","人物","口播","主播","真人","采访","露脸","自拍","人脸","人体"]
    combined = (tags + " " + objects + " " + video_path).lower()
    return 1 if any(kw in combined for kw in human_kw) else 0


class VideoAnalyzer:
    """
    视频全量分析调度器 — 管理多模型并行执行。
    v11.1: 强制 Qwen3-VL-4B 视觉模型，已移除 CLIP/YOLO 死代码。

    流水线:
      1. 抽帧 (每秒1帧, 最多60帧)
      2. 并行: Qwen3-VL-4B (强制本地模型)
      3. 并行: Whisper 语音转文字 + 音频分类
      4. TagMerger 融合汇总
      5. 返回 VideoAnalysisResult
    """

    def __init__(self, db_path: str = None, progress_callback: Callable = None):
        self.frame_extractor = FrameExtractor()
        self.vision = VisionModel()  # v11.0: 强制 Qwen3-VL-4B，无降级
        self.whisper = WhisperModel()
        self.audio_classifier = AudioClassifier()
        self.tag_merger = TagMerger()
        self.db_path = db_path
        self.progress_callback = progress_callback
        self._cancel = False
        self._pool = None  # 线程池复用 — 延迟创建

    def _get_pool(self, max_workers=2):
        """获取复用的线程池（延迟创建，避免未使用时的开销）"""
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=max_workers)
        return self._pool

    def cancel(self):
        self._cancel = True
        if self._pool:
            self._pool.shutdown(wait=False)
            self._pool = None

    # 统一视觉模型 (VisionModel) — 首次调用自动加载 Qwen3/Florence/Ollama

    def analyze(self, video_path: str, source_folder: str = "") -> Optional[Dict]:
        self._cancel = False
        path = Path(video_path); fname = path.name
        if self.progress_callback: self.progress_callback("抽帧中...", fname, 0.0)

        frames = self.frame_extractor.extract_by_interval(video_path, interval_sec=1.0, max_frames=60)
        if not frames or self._cancel: return None

        if self.progress_callback: self.progress_callback("画面分析中...", fname, 0.2)

        vl_results = []; key_frames = self._select_key_frames(frames, max_n=6)

        pool = self._get_pool(max_workers=2)
        futures = {}
        for f in key_frames[:4]:
            futures[pool.submit(self._run_vision, f)] = ("vision", f)
        for future in as_completed(futures):
            if self._cancel: pool.shutdown(wait=False); return None
            try:
                mt, result = future.result()
                if mt == "vision" and result: vl_results.append(result)
            except Exception: pass  # 单帧识别失败不阻塞整体流程

        # Step 3: 并行音频分析
        if self.progress_callback:
            self.progress_callback("音频分析中...", fname, 0.6)

        whisper_result = AudioResult()
        audio_class_result = {}
        pool2 = self._get_pool(max_workers=2)
        f_whisper = pool2.submit(self._run_whisper, video_path)
        f_audio = pool2.submit(self._run_audio_classifier, video_path)
        try:
            whisper_result = f_whisper.result(timeout=120)
        except Exception:
            pass
        try:
            audio_class_result = f_audio.result(timeout=30)
        except Exception:
            pass

        if self._cancel: return None

        # Step 4: 融合汇总
        if self.progress_callback:
            self.progress_callback("融合标签中...", fname, 0.8)

        # 汇总VL结果
        vl_merged = {"objects": [], "materials": [], "colors": [], "style": "", "scene_type": ""}
        for vr in vl_results:
            if isinstance(vr, dict):
                for k in vl_merged:
                    if k in vr and isinstance(vr[k], list):
                        vl_merged[k].extend(vr[k])
                    elif k in vr and vr[k]:
                        vl_merged[k] = vr[k]

        # CLIP向量 和 YOLO 物体检测 — 由 VisionUnified 统一处理
        # 此处保留空列表作为 fallback，实际向量/物体由 vision_unified 模块提供
        avg_embedding = None
        yolo_objects = []

        # 融合
        tags = self.tag_merger.merge(
            vl_result=vl_merged,
            yolo_objects=yolo_objects,
            whisper_text=whisper_result.transcript if whisper_result else "",
            filename=fname
        )

        # 清理临时帧文件
        if frames:
            tmpdir = os.path.dirname(frames[0].path)
            self.frame_extractor.cleanup(tmpdir)

        if self.progress_callback:
            self.progress_callback("完成", fname, 1.0)

        # 获取视频信息
        stat = path.stat()

        # 生成密集字幕
        dense_caption = self._generate_dense_caption(tags, whisper_result, video_path)

        return {
            "video_path": video_path,
            "dense_caption": dense_caption,
            "source_folder": source_folder,
            "start_time": 0,
            "end_time": self.frame_extractor._get_duration(video_path),
            "tags": tags.get("tags", ""),
            "objects": tags.get("objects", ""),
            "style": tags.get("style", ""),
            "color": tags.get("color", ""),
            "material": tags.get("material", ""),
            "speech_text": whisper_result.transcript if whisper_result else "",
            "confidence": tags.get("confidence", 0.0),
            "embedding": avg_embedding,
            "duration": self.frame_extractor._get_duration(video_path),  # 实际视频时长(秒)
            "file_size": stat.st_size,
            "file_mtime": stat.st_mtime,
        }

    def _select_key_frames(self, frames: List[FrameInfo], max_n: int = 6) -> List[FrameInfo]:
        """选择关键帧：均匀分布"""
        if len(frames) <= max_n:
            return frames
        step = len(frames) / max_n
        return [frames[int(i * step)] for i in range(max_n)]

    def _run_vision(self, frame: FrameInfo):
        """统一视觉模型推理"""
        if self.vision.available:
            return ("vision", self.vision.analyze(frame.path))
        return ("vision", {})

    def _run_whisper(self, video_path: str):
        return self.whisper.transcribe(video_path)

    def _run_audio_classifier(self, video_path: str):
        return self.audio_classifier.classify(video_path)

    def _generate_dense_caption(self, tags: dict, whisper_result, video_path: str) -> str:
        """生成密集自然语言字幕描述"""
        try:
            from core.multimodal_embedding import MultimodalEmbedding
            embedder = MultimodalEmbedding()
            audio_tags = {"emotion": getattr(whisper_result, "ambient_type", "")} if whisper_result else None
            return embedder.generate_dense_caption(
                vision_tags=tags,
                audio_tags=audio_tags,
                video_path=video_path
            )
        except Exception:
            # 降级：简单拼接标签
            parts = []
            for key in ["objects","materials","colors","style","scene_type"]:
                val = tags.get(key, "")
                if val:
                    parts.append(val if isinstance(val, str) else ",".join(val[:3]))
            return "岛台展示: " + "; ".join(parts[:3]) if parts else Path(video_path).stem[:60]
