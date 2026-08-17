"""
树剪 — 多模态密集字幕生成引擎 v10.4
融合视觉标签 + 音频情绪 → 生成自然语言描述 → 文本嵌入向量
用于升级后的智能匹配 (替换旧关键词匹配)
"""
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional


class MultimodalEmbedding:
    """多模态嵌入 — 视觉+音频+文本联合编码"""

    def __init__(self):
        self._text_encoder = None
        self.dim = 1024  # BGE-M3 输出维度

    @property
    def text_encoder(self):
        if self._text_encoder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._text_encoder = SentenceTransformer("BAAI/bge-m3")
            except ImportError:
                pass
        return self._text_encoder

    @property
    def available(self) -> bool:
        return self.text_encoder is not None

    def encode_clip(self, video_path: str, vision_tags: dict,
                    audio_tags: dict = None) -> Optional[List[float]]:
        """生成视觉+音频的联合嵌入向量"""
        parts = []
        if vision_tags:
            for cat in ["objects", "materials", "colors", "style", "scene_type"]:
                val = vision_tags.get(cat, "")
                if isinstance(val, list):
                    parts.extend(val)
                elif val:
                    parts.append(str(val))
        if audio_tags:
            emotion = audio_tags.get("emotion", "")
            if emotion:
                parts.append(emotion)
        combined = " ".join(parts)
        if not combined.strip():
            return None
        if self.text_encoder:
            vec = self.text_encoder.encode(combined)
            return vec.tolist()
        return None

    def generate_dense_caption(self, vision_tags: dict, audio_tags: dict = None,
                               video_path: str = "") -> str:
        """从视觉+音频标签生成密集字幕（自然语言描述）"""
        objects = vision_tags.get("objects", [])
        materials = vision_tags.get("materials", [])
        colors = vision_tags.get("colors", [])
        style = vision_tags.get("style", "")
        scene = vision_tags.get("scene_type", "")

        parts = []
        if style:
            parts.append(f"{style}风格")
        if scene:
            parts.append(f"{scene}")
        if materials:
            parts.append(f"{'和'.join(materials[:3])}材质")
        if colors:
            parts.append(f"{'、'.join(colors[:3])}色调")
        if objects:
            parts.append(f"展示{'、'.join(objects[:5])}等细节")
        if audio_tags:
            emotion = audio_tags.get("emotion", "")
            if emotion:
                parts.append(f"情绪:{emotion}")
        if not parts:
            name = Path(video_path).stem if video_path else ""
            return f"岛台展示视频: {name[:60]}"
        return "，".join(parts) + "。"

    def encode_text(self, text: str) -> Optional[List[float]]:
        """编码文本为嵌入向量"""
        if self.text_encoder and text.strip():
            return self.text_encoder.encode(text).tolist()
        return None

    def similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """计算余弦相似度"""
        a, b = np.array(vec_a), np.array(vec_b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


# 全局实例
_embedder: Optional[MultimodalEmbedding] = None


def get_embedder() -> MultimodalEmbedding:
    global _embedder
    if _embedder is None:
        _embedder = MultimodalEmbedding()
    return _embedder
