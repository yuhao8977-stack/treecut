#!/usr/bin/env python3
"""
V3 → V5 数据库统一迁移脚本
将 ai_material_library.db (V3) 的数据迁移到新统一 schema (V5)
运行: python migrate_v3_to_v5.py --dry-run  # 预览
      python migrate_v3_to_v5.py --apply    # 执行迁移
"""
import sys, sqlite3, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))


def get_v3_stats(db_path):
    """获取V3数据库统计"""
    with sqlite3.connect(db_path) as conn:
        mats = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
        vids = conn.execute("SELECT COUNT(*) FROM video_registry").fetchone()[0]
        analyzed = conn.execute("SELECT COUNT(*) FROM video_registry WHERE analyzed=1").fetchone()[0]
    return {"segments": mats, "videos": vids, "analyzed": analyzed}


def get_v5_stats(db_path):
    """获取V5数据库统计"""
    try:
        with sqlite3.connect(db_path) as conn:
            mats = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
        return {"segments": mats}
    except Exception:
        return {"segments": 0}


def migrate(apply: bool = False):
    """执行V3→V5统一迁移"""
    from core.config import get_config
    cfg = get_config()

    v3_db = cfg.material_db_path
    v5_dir = Path(__file__).parent / "material_engine_v3" / "database"
    v5_db = str(v5_dir / "material_v3.db")  # V3和V5已统一，使用同一个数据库

    print("=" * 60)
    print("  V3 → V5 数据库统一迁移")
    print("=" * 60)

    v3_stats = get_v3_stats(v3_db)
    v5_stats = get_v5_stats(v5_db)

    print(f"\n  V3 数据库: {v3_db}")
    print(f"    素材片段: {v3_stats['segments']:,}")
    print(f"    注册视频: {v3_stats['videos']:,}")
    print(f"    已分析:   {v3_stats['analyzed']:,}")

    print(f"\n  V5 数据库: {v5_db}")
    print(f"    素材片段: {v5_stats['segments']:,}")

    if not apply:
        print(f"\n  🔍 [DRY RUN] 使用 --apply 执行实际迁移")
        print(f"  迁移策略: 将 V3 数据同步到 V5 schema，保留 V3 作为备份")
        return

    # 初始化V5 schema
    print(f"\n  🔧 初始化 V5 schema...")
    try:
        from material_engine_v5.database.schema_v5 import init_v5
        init_v5()
        print(f"  ✅ V5 schema 已初始化")
    except Exception as e:
        print(f"  !! V5 schema 初始化失败: {e}")
        return

    # 迁移数据
    print(f"\n  📦 迁移数据...")
    migrated = 0
    with sqlite3.connect(v3_db) as src, sqlite3.connect(v5_db) as dst:
        rows = src.execute(
            "SELECT video_path, start_time, end_time, tags, objects, style, color, material, speech_text, confidence, source_folder, duration, file_size, file_mtime FROM materials"
        ).fetchall()

        for row in rows:
            try:
                dst.execute("""
                    INSERT OR IGNORE INTO materials
                    (video_path, start_time, end_time, tags, objects, style, color, material, speech_text, confidence, source_folder, duration, file_size, file_mtime, analyzed)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                """, row)
                migrated += 1
            except Exception:
                pass

        dst.commit()

    v5_new = get_v5_stats(v5_db)
    print(f"  ✅ 迁移完成: {migrated:,} 条 → V5 ({v5_new['segments']:,} 总计)")

    print(f"\n  📝 后续步骤:")
    print(f"    1. V3 数据库保留为备份: {v3_db}")
    print(f"    2. 更新 modules/shared/config.py 中的 DB_PATH 指向 V5")
    print(f"    3. 验证通过后可删除 V3 数据库")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="V3→V5数据库迁移")
    p.add_argument("--apply", action="store_true", help="执行实际迁移")
    p.add_argument("--dry-run", action="store_true", default=True, help="预览模式")
    args = p.parse_args()
    migrate(apply=args.apply)
