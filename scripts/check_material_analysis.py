#!/usr/bin/env python3
"""素材分析状态诊断 — 检查 objects/标签/embedding 覆盖率"""
import sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

DB = Path("ai_material_library.db")
if not DB.exists():
    print("[FAIL] ai_material_library.db 不存在"); sys.exit(1)

conn = sqlite3.connect(str(DB))
total = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
analyzed = conn.execute("SELECT COUNT(*) FROM materials WHERE analyzed=1").fetchone()[0]
has_tags = conn.execute("SELECT COUNT(*) FROM materials WHERE tags != ''").fetchone()[0]
has_objects = conn.execute("SELECT COUNT(*) FROM materials WHERE objects != ''").fetchone()[0]
has_embed = conn.execute("SELECT COUNT(*) FROM materials WHERE embedding IS NOT NULL").fetchone()[0]
has_tags_objects = conn.execute("SELECT COUNT(*) FROM materials WHERE tags != '' AND objects != ''").fetchone()[0]

print("=" * 55)
print("  素材分析状态诊断")
print("=" * 55)
print(f"  总素材:        {total:>8,}")
print(f"  已分析:        {analyzed:>8,}  ({analyzed/max(total,1)*100:.1f}%)")
print(f"  有 tags:       {has_tags:>8,}  ({has_tags/max(total,1)*100:.1f}%)")
print(f"  有 objects:    {has_objects:>8,}  ({has_objects/max(total,1)*100:.1f}%)")
print(f"  有 tags+objects:{has_tags_objects:>8,}")
print(f"  有 embedding:  {has_embed:>8,}  ({has_embed/max(total,1)*100:.1f}%)")

# Check for human-labeled materials
human = conn.execute("""
    SELECT COUNT(*) FROM materials
    WHERE objects LIKE '%人像%' OR objects LIKE '%人物%' OR objects LIKE '%口播%'
    OR objects LIKE '%person%' OR objects LIKE '%face%'
    OR tags LIKE '%人像%' OR tags LIKE '%人物%' OR tags LIKE '%口播%'""").fetchone()[0]
print(f"  检测到人像素材: {human:>6}")

# FAISS index
faiss_path = Path("shipin/material_faiss.index")
if faiss_path.exists():
    import faiss
    idx = faiss.read_index(str(faiss_path))
    print(f"  FAISS:          {idx.ntotal:>8,} 向量, {idx.d}维")
else:
    print(f"  FAISS:          [MISSING]")

print()
if has_objects < total * 0.3:
    print("[ACTION] objects 覆盖率低 — 运行素材库扫描生成标签:")
    print("  1. 打开树剪 → 素材库 → 刷新 → 开始批量分析")
    print("  2. 或运行: python -c \"from core.analyzer import VideoAnalyzer; ...\"")
if has_embed < total * 0.1:
    print("[ACTION] embedding 覆盖率低 — 运行:")
    print("  python force_rebuild_faiss.py")
if human == 0 and has_objects > 0:
    print("[INFO] 未检测到人像标签 — 人像过滤依赖 objects 字段")
conn.close()
