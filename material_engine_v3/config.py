"""
AI Content Factory V3.0 - Central Configuration
Target: 100K+ material scale, extensible to 1M+
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# ===== Paths =====
SCAN_PATHS = [
    r"Z:\已处理素材\卖点展示类素材",
    r"Z:\已处理素材\效果展示类素材",
    r"Z:\B组更新视频",
]
DB_PATH = str(BASE_DIR / "ai_material_library.db")
V3_DB_PATH = str(Path(__file__).parent / "database" / "material_v3.db")
CACHE_DIR = Path(__file__).parent / "cache"
LOG_DIR = Path(__file__).parent / "logs"
MODEL_DIR = Path(__file__).parent / "models"
KB_DIR = Path(__file__).parent / "knowledge"

# ===== Vision Models =====
VISION_MODELS = ["qwen2.5vl:7b"]
VISION_MODEL_PRIMARY = "qwen2.5vl:7b"

# ===== OCR =====
OCR_ENGINE = "paddle"  # paddle | tesseract

# ===== Speech =====
SPEECH_MODEL = "large-v3"

# ===== Embedding =====
EMBEDDING_MODEL = "BAAI/bge-m3"

# ===== Scene Detection =====
SCENE_MIN_LENGTH = 1.0
SCENE_MAX_FRAMES = 3

# ===== Cache (SQLite-based, Redis-ready) =====
CACHE_TTL_HOURS = 168
CACHE_BACKEND = "sqlite"

# ===== Scoring =====
SCORE_WEIGHTS = {
    "clarity": 0.25,
    "stability": 0.15,
    "composition": 0.20,
    "marketing_value": 0.25,
    "industry_relevance": 0.15,
}

# ===== Task Queue =====
MAX_RETRIES = 3
CHECKPOINT_INTERVAL = 10
