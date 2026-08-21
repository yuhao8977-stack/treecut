"""
V3.0 Database Schema - 12 tables for 100K+ material scale
"""
import sqlite3
from pathlib import Path
import sys; sys.path.insert(0, str(Path(__file__).parent.parent))
from config import V3_DB_PATH

def init_db(db_path=V3_DB_PATH):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript("""
        -- Core: videos
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            duration REAL, file_size INTEGER, file_mtime REAL,
            width INTEGER, height INTEGER, fps REAL,
            source_folder TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- Scene detection
        CREATE TABLE IF NOT EXISTS video_scenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER REFERENCES videos(id),
            scene_index INTEGER,
            start_time REAL, end_time REAL,
            key_frame_path TEXT,
            mid_frame_path TEXT,
            end_frame_path TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- Analysis frames
        CREATE TABLE IF NOT EXISTS video_frames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id INTEGER REFERENCES video_scenes(id),
            frame_path TEXT, frame_time REAL,
            analyzed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- 4-level unified tags
        CREATE TABLE IF NOT EXISTS video_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER REFERENCES videos(id),
            scene_id INTEGER REFERENCES video_scenes(id),
            tag_level INTEGER DEFAULT 1,
            tag_category TEXT,
            tag_value TEXT,
            tag_source TEXT,
            confidence REAL DEFAULT 0.0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- Embeddings
        CREATE TABLE IF NOT EXISTS video_embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER REFERENCES videos(id),
            scene_id INTEGER REFERENCES video_scenes(id),
            embedding BLOB,
            model_name TEXT,
            dimension INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- OCR results
        CREATE TABLE IF NOT EXISTS video_ocr (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER REFERENCES videos(id),
            scene_id INTEGER REFERENCES video_scenes(id),
            text_content TEXT,
            confidence REAL,
            language TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- Audio/speech
        CREATE TABLE IF NOT EXISTS video_audio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER REFERENCES videos(id),
            scene_id INTEGER REFERENCES video_scenes(id),
            transcript TEXT, keywords TEXT,
            language TEXT, duration REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- Quality scores
        CREATE TABLE IF NOT EXISTS video_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER REFERENCES videos(id),
            scene_id INTEGER REFERENCES video_scenes(id),
            clarity REAL, stability REAL, composition REAL,
            marketing_value REAL, industry_relevance REAL,
            total_score REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- Industry knowledge base
        CREATE TABLE IF NOT EXISTS knowledge_base (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT, subcategory TEXT,
            keyword TEXT UNIQUE, aliases TEXT,
            priority INTEGER DEFAULT 0,
            version TEXT DEFAULT '1.0',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- Custom user tags
        CREATE TABLE IF NOT EXISTS custom_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER REFERENCES videos(id),
            tag_level INTEGER, tag_category TEXT,
            tag_value TEXT, confidence REAL DEFAULT 1.0,
            source TEXT DEFAULT 'user',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- Feedback learning log
        CREATE TABLE IF NOT EXISTS feedback_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER, action TEXT,
            old_value TEXT, new_value TEXT,
            source TEXT DEFAULT 'user',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- Task queue
        CREATE TABLE IF NOT EXISTS task_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_path TEXT, task_type TEXT,
            status TEXT DEFAULT 'pending',
            priority INTEGER DEFAULT 0,
            retry_count INTEGER DEFAULT 0,
            error_msg TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            started_at TEXT, completed_at TEXT
        );

        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_videos_path ON videos(path);
        CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);
        CREATE INDEX IF NOT EXISTS idx_scenes_video ON video_scenes(video_id);
        CREATE INDEX IF NOT EXISTS idx_tags_video ON video_tags(video_id);
        CREATE INDEX IF NOT EXISTS idx_tags_value ON video_tags(tag_value);
        CREATE INDEX IF NOT EXISTS idx_tags_level ON video_tags(tag_level);
        CREATE INDEX IF NOT EXISTS idx_kb_keyword ON knowledge_base(keyword);
        CREATE INDEX IF NOT EXISTS idx_kb_category ON knowledge_base(category);
        CREATE INDEX IF NOT EXISTS idx_scores_video ON video_scores(video_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON task_queue(status);
    """)
    conn.commit()
    conn.close()
    print(f"[V3 DB] Initialized: {db_path}")

if __name__ == "__main__":
    init_db()
