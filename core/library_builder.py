"""
树剪 AI素材库 — 入库 + FAISS索引更新
SQLite 元数据存储 + 增量/全量 FAISS 向量索引
"""
import sqlite3, json, time, numpy as np, os as _os, threading as _threading
from pathlib import Path
from typing import List, Optional, Callable

_faiss_lock = _threading.Lock()  # FAISS构建锁 — 防并发写


class LibraryBuilder:
    """素材库构建器 — 写入SQLite + 更新FAISS"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "ai_material_library.db")
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS materials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_path TEXT NOT NULL,
                    start_time REAL DEFAULT 0,
                    end_time REAL DEFAULT 0,
                    tags TEXT DEFAULT '',
                    objects TEXT DEFAULT '',
                    style TEXT DEFAULT '',
                    color TEXT DEFAULT '',
                    material TEXT DEFAULT '',
                    speech_text TEXT DEFAULT '',
                    confidence REAL DEFAULT 0.0,
                    embedding BLOB DEFAULT NULL,
                    source_folder TEXT DEFAULT '',
                    duration REAL DEFAULT 0,
                    file_size INTEGER DEFAULT 0,
                    file_mtime REAL DEFAULT 0,
                    analyzed INTEGER DEFAULT 0,
                    created_time TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_video_path ON materials(video_path);
                CREATE INDEX IF NOT EXISTS idx_tags ON materials(tags);
                CREATE INDEX IF NOT EXISTS idx_analyzed ON materials(analyzed);
                CREATE TABLE IF NOT EXISTS video_registry (
                    video_path TEXT PRIMARY KEY,
                    file_mtime REAL,
                    file_size INTEGER,
                    duration REAL,
                    analyzed INTEGER DEFAULT 0,
                    last_checked TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS analysis_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_path TEXT NOT NULL,
                    models_used TEXT DEFAULT '',
                    vl_available INTEGER DEFAULT 0,
                    clip_available INTEGER DEFAULT 0,
                    whisper_available INTEGER DEFAULT 0,
                    tags_generated TEXT DEFAULT '',
                    duration_sec REAL DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
            """)

    def insert_analysis(self, data: dict, models_used: List[str] = None):
        """写入分析结果到数据库"""
        embedding_blob = None
        if data.get("embedding"):
            emb = np.array(data["embedding"], dtype=np.float32)
            embedding_blob = emb.tobytes()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO materials
                (video_path, start_time, end_time, tags, objects, style, color,
                 material, speech_text, confidence, embedding, source_folder,
                 duration, file_size, file_mtime, analyzed)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
            """, (
                data["video_path"], data.get("start_time", 0), data.get("end_time", 0),
                data.get("tags", ""), data.get("objects", ""),
                data.get("style", ""), data.get("color", ""), data.get("material", ""),
                data.get("speech_text", ""), data.get("confidence", 0.0),
                embedding_blob, data.get("source_folder", ""),
                data.get("duration", 0), data.get("file_size", 0),
                data.get("file_mtime", 0),
            ))

            # 记录分析日志
            conn.execute("""
                INSERT INTO analysis_log
                (video_path, models_used, vl_available, clip_available, whisper_available, tags_generated)
                VALUES (?,?,?,?,?,?)
            """, (
                data["video_path"],
                ",".join(models_used) if models_used else "",
                1 if "qwen_vl" in (models_used or []) else 0,
                1 if "clip" in (models_used or []) else 0,
                1 if "whisper" in (models_used or []) else 0,
                data.get("tags", "")[:200],
            ))

            # 注册视频
            conn.execute("""
                INSERT OR REPLACE INTO video_registry
                (video_path, file_mtime, file_size, duration, analyzed, last_checked)
                VALUES (?,?,?,?,1,CURRENT_TIMESTAMP)
            """, (
                data["video_path"],
                data.get("file_mtime", 0),
                data.get("file_size", 0),
                data.get("duration", 0),
            ))

    def get_stats(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
            analyzed = conn.execute("SELECT COUNT(*) FROM video_registry WHERE analyzed=1").fetchone()[0]
            total_vids = conn.execute("SELECT COUNT(*) FROM video_registry").fetchone()[0]
            logs = conn.execute("SELECT COUNT(*) FROM analysis_log").fetchone()[0]
            return {"total_segments": total, "analyzed_videos": analyzed,
                    "total_videos": total_vids, "analysis_logs": logs}

    def build_faiss_index(self, output_dir: str = None, progress: Callable = None):
        """
        全量重建 FAISS 索引 — 从数据库读取所有有效embedding，确保一致性。
        使用原子写入+文件锁: 防并发重建冲突。
        """
        if not _faiss_lock.acquire(blocking=False):
            print("   ⚠ FAISS索引正在重建中(其他任务), 跳过")
            return
        try:
            if output_dir is None:
                output_dir = str(Path(__file__).parent.parent / "shipin")
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            with sqlite3.connect(self.db_path) as conn:
                total = conn.execute("SELECT COUNT(*) FROM materials WHERE embedding IS NOT NULL AND analyzed=1").fetchone()[0]
                if total == 0:
                    print("   !! 没有可用的嵌入向量"); return
                rows = conn.execute("SELECT id, embedding FROM materials WHERE embedding IS NOT NULL AND analyzed=1").fetchall()

            ids, vectors = [], []
            for row in rows:
                if row[1]:
                    try:
                        vec = np.frombuffer(row[1], dtype=np.float32)
                        if len(vec) > 0: vectors.append(vec); ids.append(row[0])
                    except Exception as e:
                        from utils.logging import get_error_logger
                        get_error_logger().warning("FAISS", f"解析embedding失败 id={row[0]}: {e}")
            if not vectors: print("   !! 无法解析嵌入向量"); return

            try:
                import faiss
                dim = len(vectors[0])
                index = faiss.IndexFlatL2(dim)
                index.add(np.array(vectors, dtype=np.float32))

                idx_tmp = str(Path(output_dir) / "material_faiss.index.tmp")
                idmap_tmp = str(Path(output_dir) / "material_faiss_idmap.json.tmp")
                idx_final = str(Path(output_dir) / "material_faiss.index")
                idmap_final = str(Path(output_dir) / "material_faiss_idmap.json")

                faiss.write_index(index, idx_tmp)
                with open(idmap_tmp, "w") as f: json.dump(ids, f)

                _os.replace(idx_tmp, idx_final)
                _os.replace(idmap_tmp, idmap_final)

                if progress: progress(f"重建完成: {len(ids)}向量, {dim}维")
                print(f"   ✅ FAISS索引全量重建: {len(ids)}向量, {dim}维 (原子写入)")
            except ImportError:
                print("   !! faiss-cpu 未安装")
        finally:
            _faiss_lock.release()

    def incremental_scan(self, scan_paths: list = None):
        """
        增量扫描: 检查文件夹修改时间, 只处理新增/修改的视频。
        在数据库中记录 last_scan_mtime, 避免重复递归扫描。
        """
        if scan_paths is None:
            from core.config import SELLING_POINT_DIR, EFFECTS_DIR, B_GROUP_PATH
            scan_paths = [SELLING_POINT_DIR, EFFECTS_DIR, B_GROUP_PATH]

        import os as _os
        new_count = 0
        for sp in scan_paths:
            if not _os.path.exists(sp): continue
            folder_mtime = _os.path.getmtime(sp)
            # 检查上次扫描时间
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS scan_checkpoint (path TEXT PRIMARY KEY, last_mtime REAL)")
                row = conn.execute("SELECT last_mtime FROM scan_checkpoint WHERE path=?", (sp,)).fetchone()
                last_mtime = row[0] if row else 0
                if folder_mtime <= last_mtime:
                    continue  # 无变化, 跳过
                conn.execute("INSERT OR REPLACE INTO scan_checkpoint (path, last_mtime) VALUES (?,?)", (sp, folder_mtime))

            for root, dirs, files in _os.walk(sp):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for f in files:
                    if f.lower().endswith(('.mp4','.mov','.avi','.mkv')):
                        fp = _os.path.join(root, f)
                        mtime = _os.path.getmtime(fp)
                        with sqlite3.connect(self.db_path) as conn:
                            existing = conn.execute("SELECT file_mtime FROM video_registry WHERE video_path=?", (fp,)).fetchone()
                            if not existing or abs(existing[0] - mtime) > 1.0:
                                conn.execute("INSERT OR REPLACE INTO video_registry (video_path,file_mtime,file_size,duration,last_checked) VALUES (?,?,?,?,CURRENT_TIMESTAMP)",
                                            (fp, mtime, _os.path.getsize(fp), 0))
                                new_count += 1
        print(f"   ✅ 增量扫描: {new_count} 个新视频")
        return new_count

    def get_pending_videos(self, video_paths: List[str]) -> List[str]:
        """获取待分析的视频列表 (未在video_registry中或已被修改)"""
        pending = []
        with sqlite3.connect(self.db_path) as conn:
            for vp in video_paths:
                row = conn.execute(
                    "SELECT file_mtime FROM video_registry WHERE video_path=? AND analyzed=1", (vp,)
                ).fetchone()
                if not row:
                    pending.append(vp)
                else:
                    try:
                        current_mtime = Path(vp).stat().st_mtime
                        if abs(row[0] - current_mtime) > 1.0:
                            pending.append(vp)
                    except Exception:
                        pass
            return pending

    def mark_video_analyzed(self, video_path: str):
        """标记视频为已分析 (v11.2 后台扫描器)"""
        try:
            file_mtime = _os.path.getmtime(video_path) if _os.path.exists(video_path) else 0
            file_size = _os.path.getsize(video_path) if _os.path.exists(video_path) else 0
        except Exception:
            file_mtime = 0
            file_size = 0
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO video_registry
                (video_path, file_mtime, file_size, duration, analyzed, last_checked)
                VALUES (?,?,?,?,1,CURRENT_TIMESTAMP)
            """, (video_path, file_mtime, file_size, 0))

    def get_unanalyzed_videos(self, limit: int = 100) -> List[str]:
        """获取未分析的视频列表 (v11.2 后台扫描器)"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT video_path FROM video_registry WHERE analyzed=0 LIMIT ?",
                (limit,)
            ).fetchall()
            return [r[0] for r in rows]

    def get_analyzed_count(self) -> tuple:
        """获取分析统计 (total, analyzed) (v11.2)"""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM video_registry").fetchone()[0]
            analyzed = conn.execute(
                "SELECT COUNT(*) FROM video_registry WHERE analyzed=1"
            ).fetchone()[0]
            return (total, analyzed)
