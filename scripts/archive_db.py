#!/usr/bin/env python3
"""
树剪 TreeCut — 数据库归档脚本
================================================================
将超过指定天数的旧素材记录迁移到 archive.db 中，减小主库体积。

用法:
  python scripts/archive_db.py              # 默认归档365天之前的记录
  python scripts/archive_db.py --days 180   # 归档180天之前的
  python scripts/archive_db.py --dry-run    # 预览但不执行
"""
import sys
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "ai_material_library.db"
ARCHIVE_PATH = PROJECT_ROOT / "archive.db"


def archive(days: int = 365, dry_run: bool = False):
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    print(f"  主库: {DB_PATH}")
    print(f"  归档库: {ARCHIVE_PATH}")
    print(f"  截止日期: {cutoff} ({days}天前)")

    if not DB_PATH.exists():
        print("[ERROR] 主库不存在")
        return

    conn = sqlite3.connect(str(DB_PATH))
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = [t[0] for t in tables]
    print(f"\n  表: {table_names}")

    total_old = 0
    for tname in table_names:
        # 检查表是否有 created_time / created_at 字段
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info({tname})").fetchall()]
        time_col = None
        for tc in ["created_time", "created_at", "last_checked"]:
            if tc in cols:
                time_col = tc
                break
        if not time_col:
            print(f"  [{tname}] 无时间字段，跳过")
            continue

        count = conn.execute(
            f"SELECT COUNT(*) FROM {tname} WHERE {time_col} < ?",
            (cutoff,)
        ).fetchone()[0]
        if count > 0:
            print(f"  [{tname}] {count} 条旧记录")
            total_old += count

    conn.close()

    if total_old == 0:
        print("\n[OK] 无需要归档的旧记录")
        return

    if dry_run:
        print(f"\n[DRY-RUN] 将归档 {total_old} 条记录 (未执行)")
        return

    # 执行归档
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(f"ATTACH DATABASE '{ARCHIVE_PATH}' AS archive")

    for tname in table_names:
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info({tname})").fetchall()]
        time_col = None
        for tc in ["created_time", "created_at", "last_checked"]:
            if tc in cols:
                time_col = tc
                break
        if not time_col:
            continue

        try:
            # 创建归档表
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS archive.{tname} "
                f"AS SELECT * FROM main.{tname} WHERE 1=0"
            )
            # 迁移旧数据
            conn.execute(
                f"INSERT INTO archive.{tname} SELECT * FROM main.{tname} "
                f"WHERE {time_col} < ?", (cutoff,)
            )
            # 删除主库旧数据
            conn.execute(
                f"DELETE FROM main.{tname} WHERE {time_col} < ?", (cutoff,)
            )
            print(f"  [{tname}] 已归档并清理")
        except Exception as e:
            print(f"  [{tname}] 归档失败: {e}")

    conn.execute("VACUUM")
    conn.commit()
    conn.close()

    new_size = DB_PATH.stat().st_size / 1e6
    print(f"\n[OK] 归档完成! 主库大小: {new_size:.1f} MB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TreeCut DB Archiver")
    parser.add_argument("--days", type=int, default=365, help="多少天前的记录归档")
    parser.add_argument("--dry-run", action="store_true", help="仅预览")

    args = parser.parse_args()
    archive(days=args.days, dry_run=args.dry_run)
