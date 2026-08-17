# -*- coding: utf-8 -*-
"""
数据库核心 - v3.0 API (system.db) + v12.0 GUI 兼容层 (ai_material_library.db / material_usage.db / task_log.db)

v12.0 GUI 使用 db 单例，数据表 schema（从现有数据库提取）:
  materials(video_path,start_time,end_time,tags,objects,style,color,material,speech_text,confidence,embedding,blocked,has_frames,has_human,is_opening,analyzed,source_folder,duration,file_size,file_mtime)
  video_registry(video_path,duration,analyzed,file_mtime,file_size)
  video_annotations(video_path,video_name,frame_index,timestamp_str,frame_path,tags,model_tags,score,score_note,edited)
  annotation_feedback(video_id,old_tag,new_tag,score,user_note)
  tag_learning(tag,correct_count,total_count,accuracy)
  learned_scripts(content,source,tags,usage_count,avg_score,embedding,notes)
  generation_log(script_id,keyword,draft_dir)
  analysis_log(video_path,models_used,duration_sec,tags_generated)
  model_calls(model_name,call_type,input_summary,duration_sec,output_summary)
  model_usage_log(task_id,model_name,call_count,total_tokens)
  material_generation_log(task_id,material_path,used_at)
  ctr_feedback, trending_analysis, account_matrix
"""

import os, sqlite3, threading, time
from contextlib import contextmanager
from datetime import datetime
# ── v12.2: 连接池 (消除代码中散落的 sqlite3.connect) ──
import threading as _threading
_conn_pools = {}
_pool_lock = _threading.Lock()

def get_shared_connection(db_path: str, timeout: int = 30):
    """获取共享连接 (按线程缓存，避免高频connect/close)"""
    key = (db_path, _threading.current_thread().ident)
    with _pool_lock:
        if key not in _conn_pools:
            conn = sqlite3.connect(db_path, timeout=timeout)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            _conn_pools[key] = conn
        return _conn_pools[key]

def close_shared_connections():
    """关闭当前线程的所有共享连接"""
    tid = _threading.current_thread().ident
    with _pool_lock:
        keys_to_close = [k for k in _conn_pools if k[1] == tid]
        for k in keys_to_close:
            try:
                _conn_pools[k].close()
            except Exception:
                pass
            del _conn_pools[k]


_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# v12.0 GUI 数据库
DB_MAIN = os.path.join(_PROJ, "ai_material_library.db")
DB_USAGE = os.path.join(_PROJ, "material_usage.db")
DB_TASK = os.path.join(_PROJ, "task_log.db")

# v3.0 数据库
DB_V3 = os.path.join(_PROJ, "data", "db", "system.db")
os.makedirs(os.path.dirname(DB_V3), exist_ok=True)

COL_TIME = "datetime('now','localtime')"


class Database:
    """单例数据库管理器 - 兼容 v12.0 GUI 全部接口"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_init_done"):
            return
        self._init_done = True
        self._callbacks = []
        self._lock = threading.Lock()
        self._ensure_task_log()

    # ─── 基础方法 ───
    def exists(self):
        return os.path.exists(DB_MAIN)

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(DB_MAIN, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(self, sql, params=None):
        with self.get_connection() as conn:
            cursor = conn.execute(sql, params or ())
            return cursor.fetchall()

    # ─── 回调通知 ───
    def register_callback(self, fn):
        self._callbacks.append(fn)

    def _notify_changed(self, video_path=""):
        for cb in list(self._callbacks):
            try:
                cb(video_path)
            except Exception:
                pass

    # ─── 统计 ───
    def get_stats(self):
        try:
            with self.get_connection() as conn:
                mats = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
                analyzed = conn.execute("SELECT COUNT(*) FROM materials WHERE analyzed=1").fetchone()[0]
                videos = conn.execute("SELECT COUNT(*) FROM video_registry").fetchone()[0]
                frames = conn.execute("SELECT COUNT(*) FROM video_annotations").fetchone()[0]
                scripts = conn.execute("SELECT COUNT(*) FROM learned_scripts").fetchone()[0]
                return {
                    "total_materials": mats,
                    "analyzed": analyzed,
                    "total_videos": videos,
                    "total_frames": frames,
                    "total_scripts": scripts,
                }
        except Exception:
            return {"total_materials": 0, "analyzed": 0, "total_videos": 0, "total_frames": 0, "total_scripts": 0}

    # ─── 视频标注 ───
    def get_frames_by_video(self, video_path):
        rows = self.execute(
            "SELECT * FROM video_annotations WHERE video_path=? ORDER BY frame_index", (video_path,))
        return [dict(r) for r in rows]

    def _resolve_columns(self, table):
        """获取表实际列名"""
        with self.get_connection() as conn:
            cols = conn.execute(f"PRAGMA table_info([{table}])").fetchall()
            return [c[1] for c in cols]

    def insert_frame(self, data):
        existing_cols = self._resolve_columns("video_annotations")
        filtered = {k: v for k, v in data.items() if k in existing_cols}
        if not filtered:
            return 0
        cols_s = ", ".join(filtered.keys())
        placeholders = ", ".join(["?"] * len(filtered))
        with self.get_connection() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO video_annotations ({cols_s}) VALUES ({placeholders})",
                list(filtered.values()))
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def update_frame_score(self, frame_id, score):
        self.execute("UPDATE video_annotations SET score=?, edited=1 WHERE id=?", (score, frame_id))

    def update_frame_tags(self, frame_id, tags):
        tags_str = tags if isinstance(tags, str) else ",".join(tags) if tags else ""
        self.execute("UPDATE video_annotations SET tags=?, edited=1 WHERE id=?", (tags_str, frame_id))

    def get_all_video_frame_summaries(self, limit=200):
        rows = self.execute(
            """SELECT video_path, video_name, COUNT(*) as frame_count,
                      AVG(score) as avg_score, MAX(created_at) as last_at
               FROM video_annotations GROUP BY video_path
               ORDER BY last_at DESC LIMIT ?""", (limit,))
        return [dict(r) for r in rows]

    # ─── 反馈 ───
    def save_frame(self, video_path, video_name, ann):
        """从 FrameAnnotation 对象保存"""
        try:
            tags_str = ",".join(ann.user_tags) if hasattr(ann, 'user_tags') and ann.user_tags else ""
            orig_str = ",".join(sorted(ann.original_tags)[:10]) if hasattr(ann, 'original_tags') and ann.original_tags else ""
            score = ann.score if hasattr(ann, 'score') else 3
            note = ann.score_note if hasattr(ann, 'score_note') else ""
            ts = ann.timestamp_str if hasattr(ann, 'timestamp_str') else "00:00:00.00"
            fi = ann.frame_index if hasattr(ann, 'frame_index') else 0
            fp = ann.frame_path if hasattr(ann, 'frame_path') else ""
            self.insert_frame({
                "video_path": video_path, "video_name": video_name,
                "frame_index": fi, "timestamp_str": ts, "frame_path": fp,
                "tags": tags_str, "model_tags": orig_str,
                "score": score, "score_note": note, "edited": 1,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
        except Exception:
            pass

    def save_feedback(self, video_path, old_tag, new_tag, score, note=""):
        self.execute(
            """INSERT INTO annotation_feedback (video_id, old_tag, new_tag, score, user_note, created_at)
               VALUES (?,?,?,?,?,{})""".format(COL_TIME),
            (video_path, old_tag, new_tag, score, note))

    def get_all_feedback_stats(self, limit=50):
        rows = self.execute(
            """SELECT video_id, old_tag, new_tag, AVG(score) as avg_score,
                      COUNT(*) as cnt, MAX(created_at) as last_at
               FROM annotation_feedback GROUP BY video_id
               ORDER BY cnt DESC LIMIT ?""", (limit,))
        return [dict(r) for r in rows]

    # ─── 素材评分/拉黑 ───
    def get_lowest_rated_materials(self, limit=20):
        rows = self.execute(
            """SELECT m.video_path as path, m.id, AVG(CAST(va.score AS REAL)) as avg_score,
                      COUNT(va.id) as feedback_count
               FROM materials m
               LEFT JOIN video_annotations va ON m.video_path = va.video_path
               WHERE m.blocked = 0
               GROUP BY m.video_path
               HAVING feedback_count > 0
               ORDER BY avg_score ASC LIMIT ?""", (limit,))
        results = []
        for r in rows:
            d = dict(r)
            d.setdefault("path", d.get("video_path", ""))
            results.append(d)
        return results

    def is_material_blocked(self, path):
        rows = self.execute("SELECT blocked FROM materials WHERE video_path=? AND blocked=1", (path,))
        return len(rows) > 0

    def block_material(self, path):
        self.execute("UPDATE materials SET blocked=1 WHERE video_path=?", (path,))
        self._notify_changed(path)

    def get_material_feedback_stats(self, material_path):
        rows = self.execute(
            "SELECT AVG(CAST(score AS REAL)) as avg_score, COUNT(*) as cnt FROM video_annotations WHERE video_path=?",
            (material_path,))
        r = rows[0] if rows else None
        return dict(r) if r else {"avg_score": 0, "cnt": 0}

    def insert_material_feedback(self, path, video_log_id, fb_type, rating):
        self.execute(
            "INSERT INTO annotation_feedback (video_id, old_tag, new_tag, score, user_note, created_at) VALUES (?,?,?,?,?,{})".format(COL_TIME),
            (path, fb_type, fb_type, rating, f"video_log:{video_log_id}"))

    # ─── 学习 ───
    def update_learning(self, tag, correct=True):
        with self.get_connection() as conn:
            existing = conn.execute("SELECT id, correct_count, total_count FROM tag_learning WHERE tag=?", (tag,)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE tag_learning SET correct_count=correct_count+?, total_count=total_count+1, last_updated={} WHERE tag=?".format(COL_TIME),
                    (1 if correct else 0, tag))
            else:
                conn.execute(
                    "INSERT INTO tag_learning (tag, correct_count, total_count, accuracy, last_updated) VALUES (?,?,?,1.0,{})".format(COL_TIME),
                    (tag, 1 if correct else 0))

    def update_script_preference(self, script_hash, video_path, score):
        self.execute(
            "INSERT OR REPLACE INTO learned_scripts (content, source, tags, usage_count, avg_score, created_at, last_used_at, notes) VALUES (?,?,?,1,?,{},{},?)".format(COL_TIME, COL_TIME),
            (f"pref:{script_hash}", video_path, "", score, video_path))

    # ─── 模型调用 ───
    def record_model_call(self, model_name, call_type="analyze", input_summary="", duration_sec=0, output_summary=""):
        """记录模型调用日志。input_summary应为视频路径，output_summary为结果摘要"""
        try:
            with self.get_connection() as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS analysis_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_path TEXT, models_used TEXT, duration_sec REAL,
                    tags_generated TEXT, created_at TEXT)""")
                conn.execute(
                    "INSERT INTO analysis_log (video_path, models_used, duration_sec, tags_generated, created_at) VALUES (?,?,?,?,{})".format(COL_TIME),
                    (str(input_summary)[:300], str(model_name)[:200], duration_sec, str(call_type)[:50]))
        except Exception:
            pass

    # ─── 素材使用 (material_usage.db) ───
    def record_material_usage(self, task_id, clips_to_use):
        try:
            conn = sqlite3.connect(DB_USAGE)
            conn.execute("CREATE TABLE IF NOT EXISTS usage (video_path TEXT, task_id TEXT, used_at TEXT)")
            for clip in (clips_to_use or []):
                p = clip.get("path", str(clip)) if isinstance(clip, dict) else str(clip)
                conn.execute("INSERT OR IGNORE INTO usage (video_path, task_id, used_at) VALUES (?,?,{})".format(COL_TIME),
                             (p[:300], str(task_id)))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def get_used_material_paths(self, days=30):
        try:
            conn = sqlite3.connect(DB_USAGE)
            conn.execute("CREATE TABLE IF NOT EXISTS usage (video_path TEXT, task_id TEXT, used_at TEXT)")
            rows = conn.execute(
                "SELECT DISTINCT video_path FROM usage WHERE used_at > datetime('now','localtime','-{} days')".format(days)
            ).fetchall()
            conn.close()
            return [r[0] for r in rows]
        except Exception:
            return []

    def insert_video_log(self, task_id, keyword, draft_dir, script_id=0):
        conn = sqlite3.connect(DB_MAIN)
        conn.execute(
            "INSERT INTO generation_log (script_id, keyword, draft_dir) VALUES (?,?,?)",
            (script_id, str(keyword)[:200], str(draft_dir)[:500]))
        rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        conn.close()
        return rid

    def insert_material_log(self, video_log_id, clip, idx):
        try:
            path = clip.get("path", str(clip)) if isinstance(clip, dict) else str(clip)
            conn = sqlite3.connect(DB_MAIN)
            conn.execute("""CREATE TABLE IF NOT EXISTS material_generation_log
                (id INTEGER PRIMARY KEY AUTOINCREMENT, video_log_id INTEGER, material_path TEXT,
                 idx INTEGER, used_at TEXT)""")
            conn.execute("INSERT INTO material_generation_log (video_log_id, material_path, idx, used_at) VALUES (?,?,?,{})".format(COL_TIME),
                         (video_log_id, path[:500], idx))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def get_video_materials(self, video_log_id):
        rows = self.execute(
            "SELECT material_path as path FROM material_generation_log WHERE video_log_id=? ORDER BY idx", (video_log_id,))
        return [dict(r) for r in rows] or [{"path": ""}]

    def get_video_log(self, video_log_id):
        rows = self.execute("SELECT * FROM generation_log WHERE id=?", (video_log_id,))
        r = rows[0] if rows else {}
        return dict(r) if r else {}

    # ─── 任务记录 (task_log.db) ───
    def _ensure_task_log(self):
        if os.path.exists(DB_TASK):
            # 验证是否真的是 SQLite 文件
            try:
                conn = sqlite3.connect(DB_TASK)
                conn.execute("SELECT 1").fetchone()
                conn.close()
                return
            except Exception:
                # 文件损坏，重建
                os.remove(DB_TASK)
        conn = sqlite3.connect(DB_TASK)
        conn.execute("""CREATE TABLE IF NOT EXISTS task_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT DEFAULT 'auto', status TEXT DEFAULT '运行中',
            keyword TEXT DEFAULT '', materials_count INTEGER DEFAULT 0,
            materials_paths TEXT DEFAULT '', output_dir TEXT DEFAULT '',
            error_msg TEXT DEFAULT '', created_at TEXT, updated_at TEXT)""")
        conn.commit()
        conn.close()

    def insert_task_record(self, task_type="auto", status="运行中", keyword="", output_dir=""):
        self._ensure_task_log()
        conn = sqlite3.connect(DB_TASK)
        conn.execute(
            "INSERT INTO task_log (task_type, status, keyword, output_dir, created_at, updated_at) VALUES (?,?,?,?,{},{})".format(COL_TIME, COL_TIME),
            (task_type, status, str(keyword)[:200], str(output_dir)[:500]))
        rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        conn.close()
        return rid

    def update_task_record(self, task_id, **kwargs):
        self._ensure_task_log()
        if not kwargs:
            return
        conn = sqlite3.connect(DB_TASK)
        sets = ", ".join(f"{k}=?" for k in kwargs)
        conn.execute(f"UPDATE task_log SET {sets}, updated_at={COL_TIME} WHERE id=?",
                     list(kwargs.values()) + [task_id])
        conn.commit()
        conn.close()

    def get_task_records(self, limit=200):
        self._ensure_task_log()
        try:
            conn = sqlite3.connect(DB_TASK)
            rows = conn.execute("SELECT * FROM task_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_task_stats(self):
        self._ensure_task_log()
        try:
            conn = sqlite3.connect(DB_TASK)
            total = conn.execute("SELECT COUNT(*) FROM task_log").fetchone()[0]
            conn.close()
            return {"total": total, "success": 0, "failed": 0}
        except Exception:
            return {"total": 0, "success": 0, "failed": 0}


# ─── 全局单例 ───
db = Database()


# ═══════════════════════════════════════════════
# v3.0 兼容 API (供新插件 modules/plugins 使用)
# ═══════════════════════════════════════════════
def init_db():
    conn = sqlite3.connect(DB_V3)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS materials (id INTEGER PRIMARY KEY AUTOINCREMENT,file_path TEXT UNIQUE,file_type TEXT DEFAULT 'video',duration REAL DEFAULT 0,resolution TEXT,fps REAL DEFAULT 0,bitrate INTEGER DEFAULT 0,version INTEGER DEFAULT 1,parent_id INTEGER DEFAULT 0,create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,status TEXT DEFAULT 'pending');
    CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT,task_type TEXT DEFAULT 'full_process',material_id INTEGER,status TEXT DEFAULT 'pending',progress INTEGER DEFAULT 0,current_node TEXT,workflow_state BLOB,error_msg TEXT,create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(material_id) REFERENCES materials(id));
    CREATE TABLE IF NOT EXISTS compute_cache (id INTEGER PRIMARY KEY AUTOINCREMENT,file_hash TEXT NOT NULL,cache_type TEXT NOT NULL,cache_data TEXT NOT NULL,create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,UNIQUE(file_hash,cache_type));
    """)
    conn.commit()
    conn.close()
    return True


def execute_sql(sql, params=()):
    conn = sqlite3.connect(DB_V3)
    cursor = conn.execute(sql, params)
    conn.commit()
    rid = cursor.lastrowid
    conn.close()
    return rid


def query_sql(sql, params=()):
    conn = sqlite3.connect(DB_V3)
    cursor = conn.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    return rows
