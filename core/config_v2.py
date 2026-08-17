"""
树剪 TreeCut v11.1 — 统一配置中心 (Config Singleton)
================================================================
单一事实来源。所有配置通过 `config = Config()` 访问。
支持热重载 (`reload()`) 和观察者模式 (`observe()`)。

用法:
  from core.config_v2 import config
  api_key = config.get("DEEPSEEK_API_KEY")
  config.set("DEEPSEEK_API_KEY", "sk-new-key")  # 触发观察者通知
  config.reload()  # 从 .env 重新加载

与旧 config.py 完全兼容 — Config 实例会读取旧模块的全局变量并保持同步。
"""
import os
import json
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_PROJ_ROOT = Path(__file__).parent.parent


class Config:
    """全局配置单例 — 线程安全，支持观察者热重载"""

    _instance: Optional["Config"] = None
    _lock = threading.Lock()
    _observers: List[Callable] = []

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._data: Dict[str, Any] = {}
        self._load_from_env()
        self._load_protected_words()

    # ═══════════════════ 加载 ═══════════════════

    def _load_from_env(self):
        """从 .env 和环境变量加载所有配置"""
        # 尝试加载 .env
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=_PROJ_ROOT / ".env", override=True)
        except ImportError:
            pass

        _default_bgm_db = -8.0  # v12.0: 提取为变量，供 BGM_VOLUME 计算使用

        self._data.update({
            # 路径
            "PROJECT_ROOT": str(_PROJ_ROOT),
            "SELLING_POINT_DIR": os.environ.get("TREECUT_SELLING_DIR", r"Z:\已处理素材\卖点展示类素材"),
            "EFFECTS_DIR": os.environ.get("TREECUT_EFFECTS_DIR", r"Z:\已处理素材\效果展示类素材"),
            "B_GROUP_PATH": os.environ.get("TREECUT_BGROUP_DIR", r"Z:\B组更新视频"),
            "SCRIPT_FOLDER_PATH": os.environ.get("TREECUT_SCRIPT_DIR", r"Z:\视频脚本文件夹"),
            "OUTPUT_DRAFT_DIR": os.environ.get("TREECUT_DRAFT_DIR", str(_PROJ_ROOT / "03_粗剪输出")),
            "OUTPUT_COPY_DIR": os.environ.get("TREECUT_COPY_DIR", str(_PROJ_ROOT / "04_文案")),
            "TTS_OUTPUT_DIR": os.environ.get("TREECUT_TTS_DIR", str(_PROJ_ROOT / "05_配音")),
            "BGM_DIR": os.environ.get("TREECUT_BGM_DIR", str(_PROJ_ROOT / "02_BGM")),
            "CUSTOM_VOICE_MODEL_PATH": os.environ.get("TREECUT_VOICE_DIR", str(_PROJ_ROOT / "custom_voice" / "model")),
            "JIANGYING_DRAFT_DIR": os.path.join(os.environ.get("LOCALAPPDATA", ""),
                                                 r"JianyingPro\User Data\Projects\com.lveditor.draft"),

            # API Keys
            "DEEPSEEK_API_KEY": os.environ.get("DEEPSEEK_API_KEY", ""),
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
            "DEEPSEEK_MODEL": "deepseek-chat",
            "PIXABAY_API_KEY": os.environ.get("PIXABAY_API_KEY", ""),
            "TREECUT_WEB_PORT": int(os.environ.get("TREECUT_WEB_PORT", "7860")),
            "TREECUT_WEB_TOKEN": os.environ.get("TREECUT_WEB_TOKEN", ""),

            # 数据库路径
            "DB_MAIN": str(_PROJ_ROOT / "ai_material_library.db"),
            "DB_V3": str(_PROJ_ROOT / "material_engine_v3" / "database" / "material_v3.db"),
            "DB_USAGE": str(_PROJ_ROOT / "material_usage.db"),
            "DB_TASK": str(_PROJ_ROOT / "task_log.db"),

            # 模型配置 (强制 — 无降级)
            "VISION_MODEL": "qwen3-4b",
            "VISION_MODEL_DIR": str(_PROJ_ROOT / "models" / "Qwen3-VL-4B-Instruct-FP8"),
            "SENSEVOICE_MODEL_DIR": str(_PROJ_ROOT / "models" / "SenseVoiceSmall"),
            "TREECUT_VISION_MODEL": os.environ.get("TREECUT_VISION_MODEL", "qwen3-4b"),
            "TREECUT_ADVANCED_ANNOTATION": os.environ.get("TREECUT_ADVANCED_ANNOTATION", "true").lower() == "true",
            "TREECUT_VECTOR_BACKEND": os.environ.get("TREECUT_VECTOR_BACKEND", "faiss"),

            # 视频参数
            "VIDEO_WIDTH": 1080, "VIDEO_HEIGHT": 1920,
            "TARGET_DURATION_MIN": 23, "TARGET_DURATION_MAX": 35,
            "CLIP_DURATION_MIN": 3.0, "CLIP_DURATION_MAX": 5.0,
            "NUM_CLIPS_MIN": 5, "NUM_CLIPS_MAX": 8,
            "FPS": 30,

            # 音频参数
            "VIDEO_VOLUME": 0.0, "DEFAULT_BGM_DB": _default_bgm_db,
            # v12.0 修复: BGM_VOLUME 从 _default_bgm_db 计算，而非硬编码 -8.0
            "BGM_VOLUME": 10 ** (_default_bgm_db / 20),
            "BGM_FADE_IN": 0.05, "BGM_FADE_OUT": 0.8,
            "DEFAULT_VOICE_RATE": 1.1, "DEFAULT_VOICE_PITCH": 5,
            "TTS_VOLUME": 0.8,
            "TTS_VOICE": "zh-CN-XiaoyiNeural",
            "TTS_VOICE_ALT": "zh-CN-YunxiNeural",
            "TTS_MAX_RETRIES": 2,
            "TTS_CHARS_PER_SEC": 4.3,
            "CLEAN_PREFIX_SYMBOL": True,

            # 字幕参数
            "SUBTITLE_FONT_SIZE": 9.0,
            "SUBTITLE_STROKE_WIDTH": 45.0,
            "SUBTITLE_BACKGROUND_ENABLED": False,
            "SUBTITLE_GAP_SEC": 0.10,
            "SUBTITLE_MAX_CHARS_PER_LINE": 22,
            "SUBTITLE_POSITION_Y": -0.75,

            # 功能开关与策略参数
            "ENABLE_B_GROUP_MIX": True, "B_GROUP_RATIO": 0.3,
            "ENABLE_PERSON_FILTER": True, "PERSON_THRESHOLD": 0.8,
            "ENABLE_AUTO_TRIM_VIDEO": True, "FORCE_COMPLETE_SENTENCE": True,
            "DEFAULT_USE_CUSTOM_VOICE": True, "DEFAULT_EFFECTS_RATIO": 0.15,
            "HIGH_EFFECTS_RATIO": 0.35, "MIN_SELLING_POINTS": 3,
            "MAX_CLIPS_PER_POINT": 2, "GLOBAL_SHOW_RATIO": 0.3,
            "KEYWORD_POINT_RATIO": 0.4, "OTHER_POINTS_RATIO": 0.3,
            "GLOBAL_OPENING_SEC": 3.0, "GLOBAL_MIDDLE_SEC": 12.0,
            "GLOBAL_CLOSING_SEC_OFFSET": 6.0, "MAX_DURATION_ERROR": 0.1,
            "MIN_CTA_DURATION": 3.0, "MAX_SPEED_ADJUSTMENT": 1.05,
            "DEFAULT_COPY_DURATION": 28.0, "TRIM_FROM_END_ONLY": True,

            # 质量过滤
            "ENABLE_QUALITY_FILTER": os.environ.get("TREECUT_ENABLE_QUALITY_FILTER", "True").lower() == "true",
            "QUALITY_MIN_SCORE": float(os.environ.get("TREECUT_QUALITY_MIN_SCORE", "0.3")),
            "ENABLE_DEDUPLICATION": os.environ.get("TREECUT_ENABLE_DEDUPLICATION", "True").lower() == "true",
            "DEDUPLICATION_HAMMING_DIST": int(os.environ.get("TREECUT_DEDUPLICATION_HAMMING_DIST", "5")),

            # CTA 模板
            "CTA_KEYWORDS": [
                "评论区", "扣1", "私信", "关注", "点赞", "收藏",
                "发你", "给你", "安排", "解锁", "分享", "测评",
                "免费", "方案", "设计", "拿", "抄作业", "交流",
            ],
            "CTA_TEMPLATES": [
                "想要同款岛台的朋友,评论区扣1发你详细方案🔥",
                "喜欢这种设计吗？点个关注每天分享更多案例✨",
                "有任何问题私信我,免费给你设计专属岛台📩",
                "心动了吗？评论区告诉我,我来安排专属方案💕",
                "想抄作业的姐妹扣1,我把完整方案发给你！",
            ],

            # 文件路径
            "MATERIAL_CACHE_PATH": str(_PROJ_ROOT / "material_cache.json"),
            "MATERIAL_USAGE_DB": str(_PROJ_ROOT / "material_usage.db"),
            "BGM_LIBRARY_PATH": str(_PROJ_ROOT / "bgm_library.json"),
            "BGM_DIR_FALLBACK": str(_PROJ_ROOT / "02_BGM"),

            # 模型权重 (默认)
            "MODEL_WEIGHTS": {
                "vision": 0.40, "audio_emotion": 0.15, "audio_transcribe": 0.15,
                "knowledge": 0.20, "retrieval": 0.10,
            },
        

            # ── v12.2: 从 config.py 合并的缺失配置 ──
            "KEYWORD_FOLDER_MAP": {
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
            },
            "GENERIC_EFFECTS_FOLDERS": [
                "整体展示", "整体岛台素材", "岛台成品", "岛台工厂实拍",
                "新中式落地效果", "岛台安装效果", "厨房整体效果",
            ],
            "SCAN_BLACKLIST_DIRS": [
                "__pycache__", ".git", "node_modules", "System Volume Information",
                "$RECYCLE.BIN", "备份", "backup", "old", "archive",
            ],
            "BGM_PATH_PRIMARY": os.environ.get("TREECUT_BGM_DIR", str(_PROJ_ROOT / "02_BGM")),
            "HOOK_SEC": 8.0, "FEATURES_SEC": 12.0, "CTA_SEC": 5.0,
            "MAX_MATERIALS_PER_SCAN": int(os.environ.get("TREECUT_MAX_MATERIALS_SCAN", "5000")),

            })

        # 加载已保存的权重
        weights_file = _PROJ_ROOT / "AI素材库" / "model_weights.json"
        if weights_file.exists():
            try:
                saved = json.loads(weights_file.read_text(encoding="utf-8"))
                self._data["MODEL_WEIGHTS"].update(saved.get("weights", {}))
            except Exception:
                pass

    def _load_protected_words(self):
        words_file = _PROJ_ROOT / "protected_words.json"
        words = []
        if words_file.exists():
            try:
                data = json.loads(words_file.read_text(encoding="utf-8"))
                for wlist in data.get("categories", {}).values():
                    words.extend(wlist)
            except Exception:
                pass
        if not words:
            words = [
                "岛台", "餐边柜", "餐桌", "高柜", "酒柜", "吧台",
                "上层薄抽", "下层抽屉", "内嵌烤箱", "轨道插座", "岩板台面",
                "伸缩餐桌", "海棠角", "水磨边", "圆弧倒角", "连纹",
                "极简风", "奶油风", "侘寂风", "原木风", "轻奢风",
                "意式中古风", "法式奶油风",
            ]
        self._data["PROTECTED_WORDS"] = words

    # ═══════════════════ API ═══════════════════

    def get(self, key: str, default=None):
        """获取配置值。支持嵌套键: config.get('MODEL_WEIGHTS.vision')"""
        if "." in key:
            parts = key.split(".")
            val = self._data
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p)
                else:
                    return default
            return val if val is not None else default
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        """设置配置值并通知所有观察者"""
        self._data[key] = value
        self._notify(key, value)

    def observe(self, callback: Callable[[str, Any], None]):
        """注册观察者。回调签名: callback(key, value)"""
        self._observers.append(callback)

    def _notify(self, key: str, value: Any):
        for cb in self._observers:
            try:
                cb(key, value)
            except Exception:
                pass

    def reload(self):
        """从 .env 重新加载所有配置并通知观察者"""
        self._load_from_env()
        self._notify("_reload", None)

    def to_dict(self) -> Dict:
        """导出所有配置 (脱敏)"""
        safe = {}
        for k, v in self._data.items():
            if "KEY" in k or "TOKEN" in k:
                safe[k] = v[:8] + "****" if v and len(v) > 8 else "****"
            elif isinstance(v, (str, int, float, bool, list)):
                safe[k] = v
            else:
                safe[k] = str(v)
        return safe


# ── 全局单例 ──
config = Config()


# ── v12.2: 模块级属性兼容 (支持 from core.config_v2 import SELLING_POINT_DIR) ──
import sys as _sys

def __getattr__(name: str):
    """模块级getattr: config_v2.SELLING_POINT_DIR == config.get('SELLING_POINT_DIR')"""
    if name.startswith('_'):
        raise AttributeError(name)
    val = config.get(name)
    if val is not None:
        return val
    raise AttributeError(f"module 'core.config_v2' has no attribute '{name}'")

# 使 from core.config_v2 import * 能工作
def _get_all_keys():
    return [k for k in config._data.keys() if not k.startswith('_')]

# 注入到模块的__dir__
def __dir__():
    return list(config._data.keys())
