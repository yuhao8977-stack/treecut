"""
树剪 AI素材库 — 多模型标签融合 + 同义词去重 + 规范化
"""
import re
from typing import List, Dict, Set
from collections import defaultdict

# ── 标签规范化映射 ──
SYNONYM_MAP = {
    # 岛台类型
    "中岛台": ["中岛台", "中岛", "中央岛台", "厨房中岛"],
    "边岛台": ["边岛台", "半岛台", "靠墙岛台"],
    "吧台岛台": ["吧台岛台", "吧台", "岛台吧台"],
    "餐桌岛台一体": ["餐桌岛台一体", "岛台餐桌一体", "岛台+餐桌", "餐岛一体"],
    # 石材
    "潘多拉岩板": ["潘多拉", "潘多拉岩板", "pandora"],
    "宝格丽岩板": ["宝格丽", "宝格丽岩板", "bvlgari"],
    "鱼肚白": ["鱼肚白", "calacatta", "卡拉拉白"],
    "微水泥": ["微水泥", "micro cement", "水泥"],
    "洞石": ["洞石", "travertine", "罗马洞石"],
    "岩板": ["岩板", "sintered stone", "薄板", "通体岩板"],
    # 风格
    "奶油风": ["奶油风", "奶油色", "cream style"],
    "侘寂风": ["侘寂风", "wabi-sabi", "侘寂"],
    "极简风": ["极简风", "简约风", "现代简约", "minimalist"],
    "中古风": ["中古风", "意式中古风", "mid-century", "复古"],
    "原木风": ["原木风", "木质风", "natural wood"],
    # 功能
    "内嵌烤箱": ["内嵌烤箱", "烤箱", "嵌入式烤箱", "蒸烤一体"],
    "轨道插座": ["轨道插座", "公牛轨道插座", "移动插座"],
    "灯带": ["灯带", "感应灯带", "LED灯带", "氛围灯"],
    # 工艺
    "海棠角": ["海棠角", "45度倒角", "海棠角工艺"],
    "水磨边": ["水磨边", "水磨圆角", "圆角边"],
}

# 逆向索引: 别名 → 规范名
_ALIAS_TO_CANONICAL = {}
for canonical, aliases in SYNONYM_MAP.items():
    for alias in aliases:
        _ALIAS_TO_CANONICAL[alias.lower()] = canonical


class TagMerger:
    """多模型标签融合 — 置信度加权 + 去重 + 规范化"""

    def __init__(self):
        # 默认权重 — 可由设置页面动态覆盖
        self._weights = {
            "qwen_vl": 0.40,   # 视觉大模型 (最可靠)
            "clip": 0.25,      # 语义向量 (中等)
            "yolo": 0.10,      # 物体检测 (补充)
            "whisper": 0.15,   # 语音文本 (辅助)
            "filename": 0.10,  # 文件名 (兜底)
        }
        self._load_saved_weights()

    def _load_saved_weights(self):
        """从 model_weights.json 加载用户保存的权重"""
        try:
            from pathlib import Path as _P
            weights_file = _P(__file__).parent.parent / "AI素材库" / "model_weights.json"
            if weights_file.exists():
                import json as _j
                data = _j.loads(weights_file.read_text(encoding="utf-8"))
                saved = data.get("weights", {})
                # 类型映射: 用户类型 → 内部权重键
                type_map = {
                    "vision": "qwen_vl",
                    "audio_emotion": "clip",
                    "audio_transcribe": "whisper",
                    "knowledge": "filename",
                    "retrieval": "yolo",
                }
                for user_type, internal_key in type_map.items():
                    for name, w in saved.items():
                        info = self._get_model_type(name)
                        if info == user_type:
                            self._weights[internal_key] = float(w)
                            break
        except Exception:
            pass

    def _get_model_type(self, name: str) -> str:
        """根据模型名称推断类型"""
        name_l = name.lower()
        if any(k in name_l for k in ["qwen", "vl", "vision", "visual", "florence"]):
            return "vision"
        if any(k in name_l for k in ["sensevoice", "emotion"]):
            return "audio_emotion"
        if any(k in name_l for k in ["whisper", "transcribe"]):
            return "audio_transcribe"
        if any(k in name_l for k in ["knowledge", "bridge"]):
            return "knowledge"
        if any(k in name_l for k in ["faiss", "retrieval", "bge"]):
            return "retrieval"
        return ""

    def merge(self, vl_result: dict = None, clip_tags: List[str] = None,
              yolo_objects: List[str] = None, whisper_text: str = "",
              filename: str = "") -> dict:
        """
        融合所有模型结果，输出统一标签集。
        返回: {tags, objects, style, color, material, confidence}
        """
        tag_scores = defaultdict(float)

        # 1. Qwen2.5-VL (权重 0.40)
        if vl_result:
            self._add_tags(tag_scores, vl_result.get("objects", []), self._weights["qwen_vl"])
            self._add_tags(tag_scores, vl_result.get("materials", []), self._weights["qwen_vl"])
            self._add_tags(tag_scores, vl_result.get("colors", []), self._weights["qwen_vl"])
            if vl_result.get("style"):
                tag_scores[vl_result["style"]] += self._weights["qwen_vl"]
            if vl_result.get("scene_type"):
                tag_scores[vl_result["scene_type"]] += self._weights["qwen_vl"]

        # 2. CLIP (权重 0.25)
        if clip_tags:
            self._add_tags(tag_scores, clip_tags, self._weights["clip"])

        # 3. YOLO (权重 0.10)
        if yolo_objects:
            self._add_tags(tag_scores, yolo_objects, self._weights["yolo"])

        # 4. Whisper 文本关键词 (权重 0.15)
        if whisper_text:
            from utils.knowledge import get_bridge
            kb = get_bridge()  # 复用全局单例，避免每次重建索引
            kws = kb.extract_copy_keywords(whisper_text)
            for cat, words in kws.items():
                for w in words:
                    tag_scores[w] += self._weights["whisper"]

        # 5. 文件名 (权重 0.10)
        if filename:
            brackets = re.findall(r'【([^】]+)】', filename)
            for tag in brackets:
                for part in re.split(r'[+/\s]', tag):
                    if len(part) >= 2:
                        tag_scores[part] += self._weights["filename"]

        # ── 规范化 + 去重 ──
        merged = defaultdict(list)
        for tag, score in sorted(tag_scores.items(), key=lambda x: -x[1]):
            canonical = self._canonicalize(tag)
            if canonical and canonical not in merged.get(canonical, []):
                merged[self._categorize(canonical)].append(canonical)

        # 分类汇总
        result = {
            "tags": ",".join(merged.get("object", []) + merged.get("material", [])),
            "objects": ",".join(merged.get("object", [])),
            "style": ",".join(merged.get("style", [])),
            "color": ",".join(merged.get("color", [])),
            "material": ",".join(merged.get("material", [])),
            "confidence": round(sum(tag_scores.values()) / max(1, len(tag_scores)), 3),
            "source_count": len(tag_scores),
        }
        return result

    def _add_tags(self, scores: dict, tags: list, weight: float):
        for t in tags:
            t = str(t).strip()
            if t and len(t) >= 1:
                scores[t] += weight

    def _canonicalize(self, tag: str) -> str:
        """标签规范化"""
        return _ALIAS_TO_CANONICAL.get(tag.lower(), tag)

    def _categorize(self, tag: str) -> str:
        """标签分类"""
        style_kw = ["风", "简约", "现代", "复古", "侘寂", "轻奢", "工业", "北欧", "中式"]
        color_kw = ["白", "黑", "灰", "棕", "米", "蓝", "绿", "红", "奶", "金", "银", "哑光", "亮光", "木纹"]
        material_kw = ["岩板", "石", "木", "钢", "玻璃", "水泥", "亚克力", "陶瓷", "金属", "洞石", "微水泥"]
        object_kw = ["抽屉", "烤箱", "插座", "水槽", "灯带", "腿", "冰箱", "拉篮", "吧台", "餐桌", "酒柜", "电磁炉", "烤炉", "煮茶"]

        for kw in style_kw:
            if kw in tag: return "style"
        for kw in color_kw:
            if kw in tag: return "color"
        for kw in material_kw:
            if kw in tag: return "material"
        for kw in object_kw:
            if kw in tag: return "object"
        return "other"
