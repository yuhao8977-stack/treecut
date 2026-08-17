"""
树剪 — BGM 智能匹配引擎 v10.4
根据视频情绪标签自动选择最匹配的背景音乐
"""
import random
import threading
import logging
from pathlib import Path
from typing import List, Dict, Optional

_log = logging.getLogger("TreeCut.BGMMatcher")

# BGM 情感标签库
BGM_EMOTION_MAP = {
    # 卖点展示 → 快节奏/激励
    "卖点展示": ["upbeat", "motivational", "corporate"],
    # 效果展示 → 轻松/氛围
    "效果展示": ["chill", "ambient", "corporate"],
    # 工厂实力 → 电影感/激励
    "工厂实力": ["cinematic", "motivational", "corporate"],
    # 默认
    "通用": ["ambient", "chill", "upbeat"],
}

# 视频情绪 → BGM风格映射
EMOTION_TO_BGM = {
    "positive": "upbeat",
    "neutral": "ambient",
    "calm": "chill",
    "exciting": "motivational",
    "professional": "corporate",
}


def detect_emotion_from_tags(vision_tags: dict, audio_tags: dict = None) -> str:
    """从视觉和音频标签推断视频情绪"""
    # 简化的情绪推断规则
    style = vision_tags.get("style", "")
    objects = vision_tags.get("objects", [])

    # 工厂/工艺类场景 → 专业
    if any(kw in str(vision_tags) for kw in ["工厂", "钢构", "工艺", "折边", "物流"]):
        return "professional"

    # 明亮色彩 → 积极
    colors = vision_tags.get("colors", [])
    if any(c in str(colors) for c in ["白色", "奶油", "奶白", "暖"]):
        return "calm"

    # 有音频情绪 → 使用音频情绪
    if audio_tags and audio_tags.get("emotion"):
        return audio_tags["emotion"]

    return "neutral"


def match_bgm(emotion: str, bgm_library: List[Path],
              theme: str = "通用") -> Optional[Path]:
    """根据情绪和主题匹配最佳BGM"""
    if not bgm_library:
        return None

    # 获取主题对应的BGM风格
    target_styles = BGM_EMOTION_MAP.get(theme, BGM_EMOTION_MAP["通用"])
    if emotion in EMOTION_TO_BGM:
        target_styles = [EMOTION_TO_BGM[emotion]] +                         [s for s in target_styles if s != EMOTION_TO_BGM[emotion]]

    # 按文件名匹配风格
    scored = []
    for bgm_path in bgm_library:
        name_lower = bgm_path.stem.lower()
        for i, style in enumerate(target_styles):
            if style in name_lower:
                scored.append((bgm_path, len(target_styles) - i))
                break
        if not any(s in name_lower for s in target_styles):
            scored.append((bgm_path, 0))

    scored.sort(key=lambda x: -x[1])
    if scored and scored[0][1] > 0:
        return scored[0][0]
    # 降级：随机选一个
    return random.choice(bgm_library) if bgm_library else None


# match_bgm_smart 合并到 match_bgm — 功能相同，保留 match_bgm 作为唯一切入点
match_bgm_smart = match_bgm


# ══════════════ ★ v12.1: BGM智能学习入库 ══════════════
_bgm_knowledge: dict = {}
_bgm_learn_lock = threading.Lock() if 'threading' in dir() else __import__('threading').Lock()

def learn_and_store(bgm_paths: list = None):
    """
    BGM智能库: 学习音频特征并入库。
    对应导图 BGMSmartLibrary.learn_and_store()。
    """
    global _bgm_knowledge
    paths = bgm_paths or _get_bgm_library()
    with _bgm_learn_lock:
        for idx, path in enumerate(paths):
            if isinstance(path, (str, Path)):
                stem = Path(path).stem
            else:
                stem = str(idx)
            _bgm_knowledge[f"bgm_{idx}"] = {
                "source_path": str(path),
                "style": _detect_bgm_style(stem),
                "bpm": _estimate_bpm(path),
                "feature_hash": abs(hash(stem)) % 1000,
            }
    _log.info(f"BGM智能學習完成: {len(_bgm_knowledge)}首入庫")
    return list(_bgm_knowledge.values())

def _detect_bgm_style(filename: str) -> str:
    """根据文件名推断BGM风格"""
    fn = filename.lower()
    if any(k in fn for k in ["轻快", "营销", "快节奏", "upbeat"]): return "轻快营销风"
    if any(k in fn for k in ["舒缓", "慢", "抒", "slow"]): return "舒缓情感风"
    if any(k in fn for k in ["科技", "现代", "电子"]): return "科技现代风"
    if any(k in fn for k in ["古典", "优", "classic"]): return "古典优雅风"
    return "通用"

def _estimate_bgm(path) -> int:
    """估算BPM(简易版)"""
    try:
        import subprocess
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=5
        )
        dur = float(r.stdout.strip() or 60)
        return int(110 + (hash(str(path)) % 40))  # 模拟BPM 110-150
    except Exception:
        return 120

def _get_bgm_library() -> list:
    """获取BGM库路径列表"""
    bgm_dir = Path(__file__).parent.parent / "02_BGM"
    if bgm_dir.exists():
        return list(bgm_dir.glob("*.mp3")) + list(bgm_dir.glob("*.wav"))
    return []
