"""
树剪 — 使用记录自动收集系统
全局操作记录: 标签标注/脚本修改/视频生成/模型打分/错误日志
"""
import os, json, time, sqlite3, threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
from collections import defaultdict

DATA_DIR = Path("AI素材库/使用记录")
DATA_DIR.mkdir(parents=True, exist_ok=True)

class UsageRecorder:
    """全局操作记录收集器 — 线程安全"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._enabled = True  # 总开关
        self._collect_types = {  # 分类开关
            "annotation": True,   # 标签标注记录
            "script": True,       # 脚本修改记录
            "generation": True,   # 视频生成记录
            "scoring": True,      # 模型打分记录
            "error": True,        # 错误日志
        }
        self._auto_learn = True
        self._learn_time = "02:00"  # 默认凌晨2点
        self._records: List[Dict] = []
        self._db_path = str(DATA_DIR / "usage_log.db")
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS usage_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT, action TEXT, detail TEXT, metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS learning_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT, rule TEXT, source TEXT, confidence REAL,
                applied INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )""")

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, val: bool):
        self._enabled = val

    def record(self, rec_type: str, action: str, detail: str = "", metadata: Dict = None):
        """记录一条操作"""
        if not self._enabled or not self._collect_types.get(rec_type, True):
            return
        entry = {
            "type": rec_type, "action": action, "detail": detail[:500],
            "metadata": json.dumps(metadata or {}, ensure_ascii=False),
            "timestamp": datetime.now().isoformat(),
        }
        with self._lock:
            self._records.append(entry)
            if len(self._records) > 1000:
                self._records = self._records[-500:]

        # Synchronous write (fast enough for SQLite WAL mode; thread-safe)
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "INSERT INTO usage_records (type, action, detail, metadata) VALUES (?,?,?,?)",
                    (rec_type, action, detail[:500], json.dumps(metadata or {}, ensure_ascii=False))
                )
                conn.commit()
        except Exception: pass  # non-critical fallback — DB write failure should not block

    def record_annotation(self, video_name: str, frame_count: int, edited_count: int):
        self.record("annotation", "标注完成", f"{video_name}: {edited_count}/{frame_count}帧修正",
                   {"video": video_name, "frames": frame_count, "edited": edited_count})

    def record_generation(self, keyword: str, copy_len: int, duration: float):
        self.record("generation", "视频生成", f"关键词={keyword}, 文案{copy_len}字, {duration:.1f}s",
                   {"keyword": keyword, "copy_len": copy_len, "duration": duration})

    def record_generation_with_details(self, keyword: str, script_id: int = None,
                                       clip_paths: List[str] = None, copy_text: str = "",
                                       duration: float = 0, tts_duration: float = 0):
        """记录详细的生成信息到 usage_records 和 generation_log"""
        metadata = {
            "keyword": keyword, "script_id": script_id,
            "clip_count": len(clip_paths) if clip_paths else 0,
            "total_duration": duration, "tts_duration": tts_duration,
        }
        self.record("generation", "视频生成详细",
                    f"关键词={keyword}, 脚本#{script_id}, 素材数={len(clip_paths) if clip_paths else 0}",
                    metadata=metadata)
        try:
            from core.database import db
            with db.get_connection() as conn:
                conn.execute("""
                    INSERT INTO generation_log (script_id, keyword, draft_dir, copy_text, score, created_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (script_id, keyword, "", (copy_text or "")[:200], 3))
        except Exception:
            pass

    def record_scoring(self, model_name: str, avg_score: float, frame_count: int):
        self.record("scoring", "模型打分", f"{model_name}: {avg_score}/5 ({frame_count}帧)",
                   {"model": model_name, "avg_score": avg_score, "frames": frame_count})

    def record_error(self, module: str, error_msg: str):
        self.record("error", "错误", f"[{module}] {error_msg[:200]}",
                   {"module": module, "error": error_msg[:300]})

    def get_stats(self) -> Dict:
        """获取统计信息"""
        try:
            with sqlite3.connect(self._db_path) as conn:
                total = conn.execute("SELECT COUNT(*) FROM usage_records").fetchone()[0]
                types = {}
                for t in ["annotation","script","generation","scoring","error"]:
                    cnt = conn.execute("SELECT COUNT(*) FROM usage_records WHERE type=?", (t,)).fetchone()[0]
                    types[t] = cnt
                rules = conn.execute("SELECT COUNT(*) FROM learning_rules").fetchone()[0]
                # 数据大小
                db_size = Path(self._db_path).stat().st_size if Path(self._db_path).exists() else 0
                return {"total": total, "by_type": types, "learning_rules": rules, "size_kb": round(db_size/1024, 1)}
        except Exception:
            return {"total": 0, "by_type": {}, "learning_rules": 0, "size_kb": 0}

    def export_csv(self, output_path: str = None) -> str:
        """导出记录为CSV"""
        if output_path is None:
            output_path = str(DATA_DIR / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute("SELECT type, action, detail, created_at FROM usage_records ORDER BY id").fetchall()
            with open(output_path, "w", encoding="utf-8-sig") as f:
                f.write("类型,操作,详情,时间\n")
                for r in rows:
                    f.write(f'"{r[0]}","{r[1]}","{r[2]}","{r[3]}"\n')
            return output_path
        except Exception as e:
            return f"导出失败: {e}"

    def clear_records(self):
        """清空所有记录"""
        with self._lock:
            self._records = []
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("DELETE FROM usage_records")
                conn.commit()
        except Exception: pass  # non-critical fallback  # non-critical fallback

    def get_recent(self, limit: int = 50) -> List[Dict]:
        """获取最近记录"""
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT type, action, detail, created_at FROM usage_records ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            return [{"type": r[0], "action": r[1], "detail": r[2], "time": r[3]} for r in rows]
        except Exception:
            return []

    def add_learning_rule(self, category: str, rule: str, source: str = "DeepSeek", confidence: float = 0.5):
        """添加学习规则"""
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "INSERT INTO learning_rules (category, rule, source, confidence) VALUES (?,?,?,?)",
                    (category, rule, source, confidence)
                )
        except Exception: pass  # non-critical fallback  # non-critical fallback

    def get_learning_rules(self) -> List[Dict]:
        """获取学习规则"""
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT category, rule, source, confidence, applied FROM learning_rules ORDER BY confidence DESC"
                ).fetchall()
            return [{"category": r[0], "rule": r[1], "source": r[2], "confidence": r[3], "applied": r[4]} for r in rows]
        except Exception:
            return []


# 全局单例
_recorder: Optional[UsageRecorder] = None

def get_recorder() -> UsageRecorder:
    global _recorder
    if _recorder is None:
        _recorder = UsageRecorder()
    return _recorder
