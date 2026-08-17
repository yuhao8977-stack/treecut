"""
树剪 TreeCut — 核心引擎
用法: from core import run, generate_tts_voiceover, ...
"""
import sys, os
from pathlib import Path

# Windows GBK 修复
if sys.platform == "win32":
    try:
        if sys.stdout is not None:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr is not None:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception as _e:
        try:
            from utils.logging import log_warning
            log_warning('__init__', str(_e)[:80])
        except Exception:
            pass

# .env 加载
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=False)
except ImportError: pass

# 核心模块导出
from core.config import *
from core.copywriter import *
from core.tts import *
from core.draft import *
from core.pipeline import (
    run, run_multi, run_batch,
    print_banner, print_clip_table, save_copy,
    list_available_selling_points,
    collect_multi_point_mp4s,
    collect_effects_mp4s, collect_b_group_mp4s,
    collect_multi_selling_mp4s,
    match_clips_to_sentences,
    find_closest_folder,
    collect_bgm, list_all_mp4, detect_video_theme,
    build_tts_synced_timeline, validate_draft,
    get_script_row, read_script_excel,
    generate_copy, generate_fallback_copy,
    split_copy_to_subtitles, clean_text_for_tts,
    generate_tts_voiceover, get_audio_duration_seconds,
    JianyingDraftBuilder, save_draft, sec_to_us,
    ai_match_clips,
)

# 素材使用追踪
import sqlite3 as _sql
import hashlib as _hashlib
from datetime import datetime as _dt

class MaterialCacheManager:
    CACHE_PATH = _PROJECT_ROOT / "material_cache.json"
    @staticmethod
    def _dir_fingerprint(dirs):
        sig = ""
        for d in dirs:
            p = Path(d)
            if p.exists(): sig += f"{d}:{p.stat().st_mtime:.0f};"
        return _hashlib.md5(sig.encode()).hexdigest()[:12]
    @classmethod
    def load(cls, scan_dirs):
        import json as _j
        try:
            if not cls.CACHE_PATH.exists(): return None
            with open(cls.CACHE_PATH, "r", encoding="utf-8") as f: data = _j.load(f)
            if data.get("fingerprint") != cls._dir_fingerprint(scan_dirs): return None
            return data
        except Exception: return None
    @classmethod
    def save(cls, scan_dirs, cache_data):
        import json as _j
        try:
            cls.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            cache_data["fingerprint"] = cls._dir_fingerprint(scan_dirs)
            cache_data["saved_at"] = _dt.now().isoformat()
            with open(cls.CACHE_PATH, "w", encoding="utf-8") as f: _j.dump(cache_data, f, ensure_ascii=False, indent=2)
        except Exception as _e: from utils.logging import log_warning; log_warning('__init__', str(_e)[:80])
    @classmethod
    def invalidate(cls):
        try: cls.CACHE_PATH.unlink(missing_ok=True); print("   [Cache] Cleared")
        except Exception as _e: from utils.logging import log_warning; log_warning('__init__', str(_e)[:80])

class MaterialUsageTracker:
    DB_PATH = _PROJECT_ROOT / "material_usage.db"
    @classmethod
    def _get_conn(cls):
        cls.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = _sql.connect(str(cls.DB_PATH))
        conn.execute("CREATE TABLE IF NOT EXISTS usage (path TEXT PRIMARY KEY, count INTEGER DEFAULT 0, last_used TEXT)")
        conn.commit(); return conn
    @classmethod
    def record_usage(cls, paths):
        try:
            conn = cls._get_conn(); now = _dt.now().isoformat()
            for p in paths:
                conn.execute("INSERT INTO usage(path,count,last_used) VALUES(?,1,?) ON CONFLICT(path) DO UPDATE SET count=count+1,last_used=?", (str(p), now, now))
            conn.commit(); conn.close()
        except Exception as _e: from utils.logging import log_warning; log_warning('__init__', str(_e)[:80])
    @classmethod
    def get_usage_count(cls, path):
        try:
            conn = cls._get_conn(); row = conn.execute("SELECT count FROM usage WHERE path=?", (str(path),)).fetchone()
            conn.close(); return row[0] if row else 0
        except Exception: return 0
    @classmethod
    def sort_by_freshness(cls, mp4_pool):
        try:
            counts = {p: cls.get_usage_count(p) for p in mp4_pool}
            return sorted(mp4_pool, key=lambda p: counts.get(p, 0))
        except Exception: return mp4_pool
    @classmethod
    def print_stats(cls, top_n=10):
        try:
            conn = cls._get_conn()
            rows = conn.execute("SELECT path,count,last_used FROM usage ORDER BY count DESC LIMIT ?", (top_n,)).fetchall()
            conn.close()
            if rows:
                print(f"\n   [UsageStats] Top {len(rows)} most-used clips:")
                for path, count, last_used in rows:
                    print(f"      {count:3d}x | {Path(path).name[:45]} | {last_used[:10]}")
        except Exception as _e: from utils.logging import log_warning; log_warning('__init__', str(_e)[:80])

__version__ = "12.1.0"
