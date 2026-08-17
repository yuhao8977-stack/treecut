"""Task Queue V3.0 - SQLite-backed, Celery-ready interface"""
import sys, sqlite3
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent.parent))
from material_engine_v3.config import V3_DB_PATH
MAX_RETRIES = 3

class TaskQueue:
    def __init__(self, db_path=V3_DB_PATH):
        self.db_path = db_path

    def enqueue(self, video_path, task_type, priority=0):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""INSERT INTO task_queue (video_path, task_type, priority)
                VALUES (?,?,?)""", (video_path, task_type, priority))
            conn.commit()

    def dequeue(self, task_type=None, limit=1):
        with sqlite3.connect(self.db_path) as conn:
            query = """SELECT id, video_path, task_type FROM task_queue
                WHERE status='pending' AND retry_count < ?"""
            params = [MAX_RETRIES]
            if task_type:
                query += " AND task_type=?"; params.append(task_type)
            query += " ORDER BY priority DESC LIMIT ?"; params.append(limit)
            rows = conn.execute(query, params).fetchall()
            for r in rows:
                conn.execute("UPDATE task_queue SET status='running', started_at=? WHERE id=?",
                             (datetime.now().isoformat(), r[0]))
            conn.commit()
            return [{"id": r[0], "path": r[1], "type": r[2]} for r in rows]

    def complete(self, task_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE task_queue SET status='done', completed_at=? WHERE id=?",
                         (datetime.now().isoformat(), task_id)); conn.commit()

    def fail(self, task_id, error=""):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""UPDATE task_queue SET status='failed', error_msg=?,
                retry_count=retry_count+1 WHERE id=?""", (error, task_id)); conn.commit()

    def stats(self):
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("""SELECT status, COUNT(*) FROM task_queue GROUP BY status""").fetchall()
