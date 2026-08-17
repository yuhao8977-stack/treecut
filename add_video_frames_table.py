"""
树剪 TreeCut v11.3 — 数据库迁移脚本
====================================
添加 video_frames 表和 has_frames 列。
运行方式: python add_video_frames_table.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "ai_material_library.db"

def migrate():
    if not DB_PATH.exists():
        print(f"数据库不存在: {DB_PATH}")
        print("请先确保程序已至少运行过一次，或手动创建数据库。")
        return

    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("PRAGMA journal_mode=WAL")

        # 检查 video_frames 表是否已存在
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='video_frames'"
        )
        if cursor.fetchone():
            print("[SKIP] video_frames 表已存在，跳过")
        else:
            print("创建 video_frames 表...")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS video_frames (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_path TEXT NOT NULL,
                    frame_timestamp REAL,
                    frame_image_path TEXT,
                    caption TEXT DEFAULT '',
                    objects TEXT DEFAULT '',
                    materials TEXT DEFAULT '',
                    colors TEXT DEFAULT '',
                    style TEXT DEFAULT '',
                    scene_type TEXT DEFAULT '',
                    user_score INTEGER DEFAULT 3,
                    user_tags TEXT DEFAULT '',
                    model_confidence REAL DEFAULT 0.8,
                    analyzed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(video_path, frame_timestamp)
                );
                CREATE INDEX IF NOT EXISTS idx_vf_path ON video_frames(video_path);
                CREATE INDEX IF NOT EXISTS idx_vf_score ON video_frames(user_score);
            """)
            print("[OK] video_frames 表已创建")

        # 检查 materials.has_frames 列
        try:
            conn.execute("SELECT has_frames FROM materials LIMIT 1")
            print("[SKIP] materials.has_frames 列已存在")
        except Exception:
            print("添加 materials.has_frames 列...")
            conn.execute("ALTER TABLE materials ADD COLUMN has_frames INTEGER DEFAULT 0")
            print("[OK] has_frames 列已添加")

        conn.commit()
        print("\n[OK] 迁移完成!")

        # 显示统计
        total_materials = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
        total_frames = conn.execute("SELECT COUNT(*) FROM video_frames").fetchone()[0]
        print(f"  素材记录: {total_materials:,}")
        print(f"  帧数据: {total_frames:,}")

    except Exception as e:
        print(f"[FAIL] 迁移失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
