# -*- coding: utf-8 -*-
"""
树剪 TreeCut v12.2 — 统一配置模块
================================
所有配置项在此定义为模块级变量，确保 `from core.config import *` 正常工作。
配置值优先从环境变量读取，其次使用 config_v2.py Config单例，最后使用硬编码默认值。

用法:
    from core.config import SELLING_POINT_DIR, DEEPSEEK_API_KEY
    from core.config import *  # 也完全正常工作

注意: config_v2.py 提供了更高级的 API (get/set/observe/reload)，推荐新代码使用。
"""
import os, json, warnings
from pathlib import Path
from typing import List, Dict

_PROJ_ROOT = Path(__file__).parent.parent

# ── 安全类型转换 ──
def _safe_env_int(key: str, default: int) -> int:
    try: return int(os.environ.get(key, str(default)))
    except (ValueError, TypeError): return default

def _safe_env_float(key: str, default: float) -> float:
    try: return float(os.environ.get(key, str(default)))
    except (ValueError, TypeError): return default

# ── 保护词加载 ──
def _load_protected_words():
    words_file = _PROJ_ROOT / "protected_words.json"
    if words_file.exists():
        try:
            data = json.loads(words_file.read_text(encoding="utf-8"))
            all_words = []
            for words in data.get("categories", {}).values():
                all_words.extend(words)
            return sorted(set(all_words), key=len, reverse=True)
        except Exception:
            pass
    return [
        "岛台", "餐边柜", "餐桌", "高柜", "酒柜", "吧台",
        "上层薄抽", "下层抽屉", "内嵌烤箱", "轨道插座", "岩板台面",
        "伸缩餐桌", "海棠角", "水磨边", "圆弧倒角", "连纹",
        "极简风", "奶油风", "侘寂风", "原木风", "轻奢风",
        "意式中古风", "法式奶油风",
    ]

# ═══════════════════════════════════════════════════════
# 路径配置
# ═══════════════════════════════════════════════════════
SELLING_POINT_DIR = os.environ.get("TREECUT_SELLING_DIR", r"Z:\已处理素材\卖点展示类素材")
EFFECTS_DIR = os.environ.get("TREECUT_EFFECTS_DIR", r"Z:\已处理素材\效果展示类素材")
B_GROUP_PATH = os.environ.get("TREECUT_BGROUP_DIR", r"Z:\B组更新视频")
SCRIPT_FOLDER_PATH = os.environ.get("TREECUT_SCRIPT_DIR", r"Z:\视频脚本文件夹")
OUTPUT_DRAFT_DIR = os.environ.get("TREECUT_DRAFT_DIR", str(_PROJ_ROOT / "03_粗剪输出"))
OUTPUT_COPY_DIR = os.environ.get("TREECUT_COPY_DIR", str(_PROJ_ROOT / "04_文案"))
TTS_OUTPUT_DIR = os.environ.get("TREECUT_TTS_DIR", str(_PROJ_ROOT / "05_配音"))
BGM_PATH_PRIMARY = os.environ.get("TREECUT_BGM_DIR", str(_PROJ_ROOT / "02_BGM"))
BGM_DIR_FALLBACK = str(_PROJ_ROOT / "02_BGM")
BGM_DIR = BGM_PATH_PRIMARY
CUSTOM_VOICE_MODEL_PATH = os.environ.get("TREECUT_VOICE_DIR", str(_PROJ_ROOT / "custom_voice" / "model"))
JIANGYING_DRAFT_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), r"JianyingPro\User Data\Projects\com.lveditor.draft")

# ═══════════════════════════════════════════════════════
# API Keys
# ═══════════════════════════════════════════════════════
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")
TREECUT_WEB_PORT = _safe_env_int("TREECUT_WEB_PORT", 7860)
TREECUT_WEB_TOKEN = os.environ.get("TREECUT_WEB_TOKEN", "")

# ═══════════════════════════════════════════════════════
# 数据库路径
# ═══════════════════════════════════════════════════════
DB_MAIN = str(_PROJ_ROOT / "ai_material_library.db")
DB_V3 = str(_PROJ_ROOT / "material_engine_v3" / "database" / "material_v3.db")
DB_USAGE = str(_PROJ_ROOT / "material_usage.db")
DB_TASK = str(_PROJ_ROOT / "task_log.db")

# ═══════════════════════════════════════════════════════
# 模型配置
# ═══════════════════════════════════════════════════════
VISION_MODEL = "qwen3-4b"
VISION_MODEL_DIR = str(_PROJ_ROOT / "models" / "Qwen3-VL-4B-Instruct-FP8")
SENSEVOICE_MODEL_DIR = str(_PROJ_ROOT / "models" / "SenseVoiceSmall")
TREECUT_VISION_MODEL = os.environ.get("TREECUT_VISION_MODEL", "qwen3-4b")
TREECUT_ADVANCED_ANNOTATION = os.environ.get("TREECUT_ADVANCED_ANNOTATION", "true").lower() == "true"
TREECUT_VECTOR_BACKEND = os.environ.get("TREECUT_VECTOR_BACKEND", "faiss")

# ═══════════════════════════════════════════════════════
# 视频参数
# ═══════════════════════════════════════════════════════
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
TARGET_DURATION_MIN = 23
TARGET_DURATION_MAX = 35
CLIP_DURATION_MIN = 3.0
CLIP_DURATION_MAX = 5.0
NUM_CLIPS_MIN = 5
NUM_CLIPS_MAX = 8
FPS = 30
DEFAULT_COPY_DURATION = 28.0
HOOK_SEC = 8.0
FEATURES_SEC = 12.0
CTA_SEC = 5.0

# ═══════════════════════════════════════════════════════
# 音频参数
# ═══════════════════════════════════════════════════════
VIDEO_VOLUME = 0.0
DEFAULT_BGM_DB = -8.0
BGM_VOLUME = 10 ** (DEFAULT_BGM_DB / 20)
BGM_FADE_IN = 0.05
BGM_FADE_OUT = 0.8
DEFAULT_VOICE_RATE = 1.1
DEFAULT_VOICE_PITCH = 5
TTS_VOLUME = 0.8
TTS_VOICE = "zh-CN-XiaoyiNeural"
TTS_VOICE_ALT = "zh-CN-YunxiNeural"
TTS_MAX_RETRIES = 2
TTS_CHARS_PER_SEC = 4.3
CLEAN_PREFIX_SYMBOL = True

# ═══════════════════════════════════════════════════════
# 字幕参数
# ═══════════════════════════════════════════════════════
SUBTITLE_FONT_SIZE = 9.0
SUBTITLE_STROKE_WIDTH = 45.0
SUBTITLE_BACKGROUND_ENABLED = False
SUBTITLE_GAP_SEC = 0.10
SUBTITLE_MAX_CHARS_PER_LINE = 22
SUBTITLE_POSITION_Y = -0.75

# ═══════════════════════════════════════════════════════
# 功能开关与策略参数
# ═══════════════════════════════════════════════════════
ENABLE_B_GROUP_MIX = True
B_GROUP_RATIO = 0.3
ENABLE_PERSON_FILTER = True
PERSON_THRESHOLD = 0.8
ENABLE_AUTO_TRIM_VIDEO = True
FORCE_COMPLETE_SENTENCE = True
DEFAULT_USE_CUSTOM_VOICE = True
DEFAULT_EFFECTS_RATIO = 0.15
HIGH_EFFECTS_RATIO = 0.35
MIN_SELLING_POINTS = 3
MAX_CLIPS_PER_POINT = 2
GLOBAL_SHOW_RATIO = 0.3
KEYWORD_POINT_RATIO = 0.4
OTHER_POINTS_RATIO = 0.3
GLOBAL_OPENING_SEC = 3.0
GLOBAL_MIDDLE_SEC = 12.0
GLOBAL_CLOSING_SEC_OFFSET = 6.0
MAX_DURATION_ERROR = 0.1
MIN_CTA_DURATION = 3.0
MAX_SPEED_ADJUSTMENT = 1.05
TRIM_FROM_END_ONLY = True

# ═══════════════════════════════════════════════════════
# 质量过滤
# ═══════════════════════════════════════════════════════
ENABLE_QUALITY_FILTER = os.environ.get("TREECUT_ENABLE_QUALITY_FILTER", "True").lower() == "true"
QUALITY_MIN_SCORE = float(os.environ.get("TREECUT_QUALITY_MIN_SCORE", "0.3"))
ENABLE_DEDUPLICATION = os.environ.get("TREECUT_ENABLE_DEDUPLICATION", "True").lower() == "true"
DEDUPLICATION_HAMMING_DIST = int(os.environ.get("TREECUT_DEDUPLICATION_HAMMING_DIST", "5"))

# ═══════════════════════════════════════════════════════
# CTA模板
# ═══════════════════════════════════════════════════════
CTA_KEYWORDS = [
    "评论区", "扣1", "私信", "关注", "点赞", "收藏",
    "发你", "给你", "安排", "解锁", "分享", "测评",
    "免费", "方案", "设计", "拿", "抄作业", "交流",
]
CTA_TEMPLATES = [
    "想要同款岛台的朋友,评论区扣1发你详细方案🔥",
    "喜欢这种设计吗？点个关注每天分享更多案例✨",
    "有任何问题私信我,免费给你设计专属岛台📩",
    "心动了吗？评论区告诉我,我来安排专属方案💕",
    "想抄作业的姐妹扣1,我把完整方案发给你！",
]

# ═══════════════════════════════════════════════════════
# 保护词
# ═══════════════════════════════════════════════════════
PROTECTED_WORDS = _load_protected_words()

# ═══════════════════════════════════════════════════════
# 关键词-文件夹映射 (pipeline.py 核心依赖)
# ═══════════════════════════════════════════════════════
KEYWORD_FOLDER_MAP = {
    "意式中古风": ["中古风", "材质细节展示"], "中古风": ["中古风", "材质细节展示"],
    "包豪斯": ["中古风", "造型展示"], "法式": ["颜色展示", "造型展示", "生活化展示"],
    "奶油风": ["颜色展示", "造型展示"], "极简风": ["造型展示", "颜色展示"],
    "原木风": ["材质细节展示", "颜色展示"], "轻奢风": ["颜色展示", "造型展示"],
    "侘寂风": ["材质细节展示", "造型展示"], "薄抽": ["上层薄抽", "下层抽屉"],
    "抽屉": ["上层薄抽", "下层抽屉", "开放抽屉"], "烤箱": ["内嵌烤箱", "内嵌电烤箱", "内嵌蒸烤一体"],
    "蒸烤": ["内嵌蒸烤一体", "内嵌烤箱"], "轨道插座": ["公牛轨道插座", "音标轨道插座", "UB克轨道插座"],
    "插座": ["公牛轨道插座", "音标轨道插座"], "水槽": ["内嵌水槽"], "灯带": ["灯带"],
    "收纳": ["上层薄抽", "下层抽屉", "单面柜储物", "对开间收纳"],
    "伸缩": ["伸缩功能", "亚克力伸缩腿"], "岩板": ["岩板台面耐造", "岩板内嵌设计", "岩板折边工艺"],
    "岛台": ["整体展示", "整体岛台素材", "岛台成品", "岛台工厂实拍"],
}

GENERIC_EFFECTS_FOLDERS = [
    "整体展示", "整体岛台素材", "岛台成品", "岛台工厂实拍",
    "新中式落地效果", "岛台安装效果", "厨房整体效果",
]

SCAN_BLACKLIST_DIRS = [
    "__pycache__", ".git", "node_modules", "System Volume Information",
    "$RECYCLE.BIN", "备份", "backup", "old", "archive",
]

# ═══════════════════════════════════════════════════════
# 扫描配置
# ═══════════════════════════════════════════════════════
SCAN_FRAME_INTERVAL = _safe_env_float("TREECUT_SCAN_FRAME_INTERVAL", 0.25)
SCAN_AUTO_START = os.environ.get("TREECUT_SCAN_AUTO_START", "false").lower() == "true"
SCAN_MAX_VIDEO_SIZE_MB = _safe_env_float("TREECUT_SCAN_MAX_VIDEO_SIZE_MB", 500.0)
SCAN_MAX_WORKERS = _safe_env_int("TREECUT_SCAN_MAX_WORKERS", 2)
MAX_MATERIALS_PER_SCAN = _safe_env_int("TREECUT_MAX_MATERIALS_SCAN", 5000)

# ═══════════════════════════════════════════════════════
# 素材使用追踪
# ═══════════════════════════════════════════════════════
MATERIAL_CACHE_PATH = str(_PROJ_ROOT / "material_cache.json")
MATERIAL_USAGE_DB = str(_PROJ_ROOT / "material_usage.db")
BGM_LIBRARY_PATH = str(_PROJ_ROOT / "bgm_library.json")
TREECUT_EXCLUDE_RECENT_SCRIPTS = _safe_env_int("TREECUT_EXCLUDE_RECENT_SCRIPTS", 5)
TREECUT_USE_FRESH_MATERIALS = os.environ.get("TREECUT_USE_FRESH_MATERIALS", "True").lower() == "true"

# ═══════════════════════════════════════════════════════
# 动态模型信息API
# ═══════════════════════════════════════════════════════
def get_active_models_info() -> List[Dict]:
    """动态获取当前实际活跃的模型列表"""
    models = []
    try:
        from core.vision_unified import get_vision_model
        vm = get_vision_model()
        models.append({"name": "Qwen3-VL-4B", "type": "vision", "weight": 0.40,
                       "enabled": vm.available, "description": "主视觉模型 (Qwen3-VL-4B-Instruct-FP8)"})
    except Exception:
        models.append({"name": "Qwen3-VL-4B", "type": "vision", "weight": 0.40,
                       "enabled": False, "description": "视觉模型未加载"})
    try:
        from core.audio_models import SenseVoiceEngine
        sv = SenseVoiceEngine()
        models.append({"name": "SenseVoice", "type": "audio_emotion", "weight": 0.15,
                       "enabled": sv.available, "description": "7种情绪检测 + 6种事件识别"})
    except Exception:
        models.append({"name": "SenseVoice", "type": "audio_emotion", "weight": 0.15,
                       "enabled": False, "description": "未加载"})
    try:
        from core.audio_models import WhisperModel
        wm = WhisperModel()
        wm._lazy_load()
        models.append({"name": "Whisper", "type": "audio_transcribe", "weight": 0.15,
                       "enabled": wm.available, "description": "语音转文字 (large-v3)"})
    except Exception:
        models.append({"name": "Whisper", "type": "audio_transcribe", "weight": 0.15,
                       "enabled": False, "description": "未加载"})
    try:
        from utils.knowledge import get_bridge
        kb = get_bridge()
        models.append({"name": "KnowledgeBridge", "type": "knowledge", "weight": 0.20,
                       "enabled": kb is not None, "description": "1200+岛台行业词汇知识库"})
    except Exception:
        models.append({"name": "KnowledgeBridge", "type": "knowledge", "weight": 0.20,
                       "enabled": False, "description": "未加载"})
    try:
        from core.smart_matcher_v3 import get_smart_matcher
        sm = get_smart_matcher()
        models.append({"name": "SmartMatcher", "type": "retrieval", "weight": 0.10,
                       "enabled": sm is not None and sm._faiss_index is not None,
                       "description": "FAISS+BGE-M3 向量检索"})
    except Exception:
        models.append({"name": "SmartMatcher", "type": "retrieval", "weight": 0.10,
                       "enabled": False, "description": "FAISS未就绪"})
    return models

def reload_config():
    """热重载配置 — 从.env重新读取"""
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=_PROJ_ROOT / ".env", override=True)
    except ImportError:
        pass
    # 重新加载关键变量
    global DEEPSEEK_API_KEY, TREECUT_WEB_PORT, TREECUT_WEB_TOKEN
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY)
    TREECUT_WEB_PORT = _safe_env_int("TREECUT_WEB_PORT", TREECUT_WEB_PORT)
    TREECUT_WEB_TOKEN = os.environ.get("TREECUT_WEB_TOKEN", TREECUT_WEB_TOKEN)
    print("   [OK] 配置已热重载")
