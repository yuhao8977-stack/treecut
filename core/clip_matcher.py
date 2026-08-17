"""
树剪 TreeCut v11.1 — CLIP 图文匹配模块 (可选加速)
================================================================
使用 OpenAI CLIP 模型计算文案与关键帧的语义相似度，
在 FAISS 向量检索之后进行二次重排序。

用法:
  from core.clip_matcher import ClipMatcher
  matcher = ClipMatcher()
  score = matcher.similarity("岛台厨房", "frame_001.jpg")
"""
import os
import numpy as np
from pathlib import Path
from typing import List, Optional, Tuple

_CLIP_AVAILABLE = False
try:
    import torch
    from PIL import Image
    from transformers import CLIPProcessor, CLIPModel
    _CLIP_AVAILABLE = True
except ImportError:
    pass


class ClipMatcher:
    """
    CLIP 图文匹配器 — 懒加载，首次使用时自动下载模型 (~600MB)

    模型: openai/clip-vit-base-patch32 (轻量，适合 CPU)
    备选: openai/clip-vit-large-patch14 (高精度，需 GPU)
    """

    _instance: Optional["ClipMatcher"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._model = None
        self._processor = None
        self._device = None
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        if not _CLIP_AVAILABLE:
            raise ImportError(
                "CLIP 匹配需要安装: pip install torch transformers Pillow"
            )

        print("   [CLIP] 加载 openai/clip-vit-base-patch32 ...")
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        model_name = "openai/clip-vit-base-patch32"
        self._processor = CLIPProcessor.from_pretrained(model_name)
        self._model = CLIPModel.from_pretrained(model_name).to(self._device)
        self._model.eval()
        self._loaded = True
        print(f"   [CLIP] 加载成功 (device={self._device})")

    @property
    def available(self) -> bool:
        return _CLIP_AVAILABLE

    def encode_text(self, text: str) -> np.ndarray:
        """将文本编码为 512 维向量"""
        self._load()
        inputs = self._processor(
            text=[text], return_tensors="pt",
            padding=True, truncation=True, max_length=77,
        ).to(self._device)
        with torch.no_grad():
            features = self._model.get_text_features(**inputs)
        return features.cpu().numpy().flatten()

    def encode_image(self, image_path: str) -> Optional[np.ndarray]:
        """将图片编码为 512 维向量"""
        self._load()
        if not os.path.exists(image_path):
            return None
        try:
            image = Image.open(image_path).convert("RGB")
        except Exception:
            return None
        inputs = self._processor(images=image, return_tensors="pt").to(self._device)
        with torch.no_grad():
            features = self._model.get_image_features(**inputs)
        return features.cpu().numpy().flatten()

    def similarity(self, text_vec: np.ndarray, image_vec: np.ndarray) -> float:
        """计算余弦相似度"""
        if text_vec is None or image_vec is None:
            return 0.0
        denom = (np.linalg.norm(text_vec) * np.linalg.norm(image_vec)) + 1e-8
        return float(np.dot(text_vec, image_vec) / denom)

    def rerank_clips(self, copy_text: str, clips: List[dict],
                     top_k: int = 8) -> List[dict]:
        """
        对候选素材进行 CLIP 二次排序。
        提取每段素材的关键帧 → 计算与文案的相似度 → 重排。
        """
        if not clips:
            return clips

        self._load()
        text_vec = self.encode_text(copy_text)

        scored = []
        for clip in clips:
            video_path = clip.get("path", "")
            if isinstance(video_path, Path):
                video_path = str(video_path)
            # 尝试找关键帧 (快速: 取视频第一帧)
            frame_path = self._get_keyframe(video_path)
            img_vec = self.encode_image(frame_path) if frame_path else None
            sim = self.similarity(text_vec, img_vec) if img_vec is not None else 0.0
            clip["clip_score"] = round(sim, 3)
            scored.append((sim, clip))

        scored.sort(key=lambda x: -x[0])
        return [s[1] for s in scored[:top_k]]

    def _get_keyframe(self, video_path: str) -> Optional[str]:
        """提取视频第一帧作为关键帧 (使用 ffmpeg)"""
        import tempfile
        import subprocess
        tmp = tempfile.mktemp(suffix=".jpg")
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", video_path, "-vframes", "1",
                 "-q:v", "2", tmp],
                capture_output=True, timeout=10,
            )
            return tmp if os.path.exists(tmp) else None
        except Exception:
            return None


# 全局单例
def get_clip_matcher() -> Optional[ClipMatcher]:
    try:
        return ClipMatcher()
    except ImportError:
        return None
