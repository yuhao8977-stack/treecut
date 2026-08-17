#!/usr/bin/env python3
"""
树剪 TreeCut v11 — 数据库迁移: 添加脚本学习库表

运行: python add_script_table.py
作用: 在 ai_material_library.db 中创建 learned_scripts 表及索引 (幂等)
"""
import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "ai_material_library.db"

SQL = """
CREATE TABLE IF NOT EXISTS learned_scripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    source TEXT DEFAULT 'manual',
    tags TEXT DEFAULT '',
    usage_count INTEGER DEFAULT 0,
    avg_score REAL DEFAULT 0.0,
    embedding BLOB DEFAULT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_used_at TEXT,
    notes TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_ls_tags ON learned_scripts(tags);
CREATE INDEX IF NOT EXISTS idx_ls_source ON learned_scripts(source);
CREATE INDEX IF NOT EXISTS idx_ls_usage ON learned_scripts(usage_count DESC);

CREATE TABLE IF NOT EXISTS generation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    script_id INTEGER,
    keyword TEXT,
    draft_dir TEXT,
    copy_text TEXT,
    score INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (script_id) REFERENCES learned_scripts(id)
);

CREATE INDEX IF NOT EXISTS idx_gl_script ON generation_log(script_id);
"""

if __name__ == "__main__":
    with sqlite3.connect(str(DB)) as conn:
        conn.executescript(SQL)
        conn.commit()
    print(f"[OK] 数据库迁移完成: {DB}")
    print(f"  learned_scripts 表已就绪")
    print(f"  generation_log 表已就绪")
