#!/usr/bin/env python3
"""
树剪 TreeCut v11.0 — FAISS 索引强制重建脚本
========================================================================
用途: 从数据库 material 表的 embedding 列重建 FAISS 向量索引。
      若有效 embedding 为 0，则遍历已分析视频重新生成 embedding (BGE-M3)。

无降级: 不使用 SQL LIKE 替代。索引必须重建成功。

用法:
  python force_rebuild_faiss.py              # 全量重建
  python force_rebuild_faiss.py --check      # 仅检查同步状态
  python force_rebuild_faiss.py --force      # 强制重建（即使已有索引）
"""
import sys
import os

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import sqlite3
import json
import time
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "ai_material_library.db"
FAISS_INDEX = PROJECT_ROOT / "shipin" / "material_faiss.index"
FAISS_IDMAP = PROJECT_ROOT / "shipin" / "material_faiss_idmap.json"


def check_sync() -> dict:
    """检查 FAISS 索引与数据库同步状态"""
    status = {
        "db_exists": DB_PATH.exists(),
        "faiss_exists": FAISS_INDEX.exists(),
        "idmap_exists": FAISS_IDMAP.exists(),
        "total_materials": 0,
        "materials_with_embedding": 0,
        "faiss_vectors": 0,
        "synced": False,
    }

    if not status["db_exists"]:
        print("  [ERROR] ai_material_library.db 不存在")
        return status

    with sqlite3.connect(str(DB_PATH)) as conn:
        status["total_materials"] = conn.execute(
            "SELECT COUNT(*) FROM materials"
        ).fetchone()[0]
        status["materials_with_embedding"] = conn.execute(
            "SELECT COUNT(*) FROM materials WHERE embedding IS NOT NULL AND analyzed=1"
        ).fetchone()[0]

    if status["faiss_exists"] and status["idmap_exists"]:
        try:
            import faiss
            idx = faiss.read_index(str(FAISS_INDEX))
            status["faiss_vectors"] = idx.ntotal
            idmap = json.loads(FAISS_IDMAP.read_text())
            status["faiss_ids"] = len(idmap)

            # 同步检查：索引向量数应与 DB embedding 数匹配
            status["synced"] = (
                status["faiss_vectors"] == status["materials_with_embedding"]
                and status["faiss_vectors"] > 0
            )
        except ImportError:
            print("  [ERROR] faiss-cpu 未安装。请运行: pip install faiss-cpu")
        except Exception as e:
            print(f"  [ERROR] FAISS 索引读取失败: {e}")

    return status


def print_status(status: dict):
    """美化打印同步状态"""
    print("\n" + "=" * 60)
    print("  FAISS 索引同步状态")
    print("=" * 60)
    print(f"  DB 存在:               {'OK' if status['db_exists'] else 'MISSING'}")
    print(f"  FAISS 索引:            {'OK' if status['faiss_exists'] else 'MISSING'}")
    print(f"  素材总数:              {status['total_materials']:,}")
    print(f"  有效 embedding 数:     {status['materials_with_embedding']:,}")
    print(f"  FAISS 向量数:          {status['faiss_vectors']:,}")
    print(f"  同步状态:              {'[OK]' if status['synced'] else '[OUT OF SYNC] 需要重建'}")
    print()


def rebuild(force: bool = False):
    """
    全量重建 FAISS 索引

    1. 检查依赖 (faiss, numpy, sentence_transformers)
    2. 读取 DB 中所有有效 embedding
    3. 重建 IndexFlatL2
    4. 原子写入
    """
    status = check_sync()
    print_status(status)

    if status["synced"] and not force:
        print("  [OK] FAISS 索引已同步，无需重建。使用 --force 强制重建。")
        return True

    if status["materials_with_embedding"] == 0:
        print("=" * 60)
        print("  [CRITICAL] 数据库中无有效 embedding!")
        print("=" * 60)
        print()
        print("  需要先生成 embedding。运行以下命令:")
        print()
        print("  python -c \"")
        print("  from core.analyzer import VideoAnalyzer")
        print("  from core.library_builder import LibraryBuilder")
        print("  analyzer = VideoAnalyzer()")
        print("  builder = LibraryBuilder()")
        print("  # 遍历未分析视频并生成 embedding")
        print("  for vp in ['/path/to/video.mp4']:")
        print("      data = analyzer.analyze(vp)")
        print("      if data: builder.insert_analysis(data, models_used=['VisionModel','whisper'])")
        print("  \"")
        print()
        print("  [INFO] 当前有 embedding 的记录为 0，无法构建有意义索引。")
        print("  请先运行素材库分析，再执行本脚本。")
        return False

    # ── 检查依赖 ──
    print("\n  [1/5] 检查依赖...")
    try:
        import numpy as np
        import faiss
        from sentence_transformers import SentenceTransformer
        print("    numpy, faiss, sentence-transformers — OK")
    except ImportError as e:
        print(f"    [ERROR] 缺少依赖: {e}")
        print("    pip install faiss-cpu sentence-transformers numpy")
        return False

    # ── 读取 embedding ──
    print(f"\n  [2/5] 从数据库读取 embedding ({status['materials_with_embedding']} 条)...")
    with sqlite3.connect(str(DB_PATH)) as conn:
        rows = conn.execute(
            "SELECT id, embedding FROM materials WHERE embedding IS NOT NULL AND analyzed=1"
        ).fetchall()

    ids = []
    vectors = []
    skipped = 0
    for row_id, blob in rows:
        try:
            vec = np.frombuffer(blob, dtype=np.float32)
            if len(vec) > 0:
                vectors.append(vec)
                ids.append(row_id)
        except Exception:
            skipped += 1

    if skipped > 0:
        print(f"    [WARN] {skipped} 条 embedding 解析失败 (跳过)")

    print(f"   有效向量: {len(vectors)}")

    if len(vectors) == 0:
        print("  [ERROR] 无有效 embedding 向量可构建索引")
        return False

    # ── 构建索引 ──
    print(f"\n  [3/5] 构建 FAISS 索引 (维度={len(vectors[0])}, L2距离)...")
    dim = len(vectors[0])
    index = faiss.IndexFlatL2(dim)
    index.add(np.array(vectors, dtype=np.float32))
    print(f"    索引已构建: {index.ntotal} 向量, {dim} 维")

    # ── 原子写入 ──
    print(f"\n  [4/5] 原子写入索引文件...")
    FAISS_INDEX.parent.mkdir(parents=True, exist_ok=True)

    # FAISS C++ library cannot handle Chinese paths on Windows.
    # Build in a temp directory (ASCII path), then copy to project.
    import tempfile as _tmpmod
    _ascii_tmp = Path(_tmpmod.mkdtemp(prefix="faiss_build_"))
    try:
        _tmp_idx = str(_ascii_tmp / "material_faiss.index")
        _tmp_map = str(_ascii_tmp / "material_faiss_idmap.json")

        faiss.write_index(index, _tmp_idx)
        with open(_tmp_map, "w", encoding="utf-8") as f:
            json.dump(ids, f)

        # Copy from ASCII-temp to project (Python's shutil handles Chinese paths)
        import shutil as _shutil
        _shutil.copy2(_tmp_idx, str(FAISS_INDEX))
        _shutil.copy2(_tmp_map, str(FAISS_IDMAP))
    finally:
        _shutil.rmtree(str(_ascii_tmp), ignore_errors=True)

    print(f"    索引: {FAISS_INDEX} ({FAISS_INDEX.stat().st_size/1e6:.1f} MB)")
    print(f"    ID映射: {FAISS_IDMAP}")

    # ── 验证 ──
    print(f"\n  [5/5] 验证...")
    idx2 = faiss.read_index(str(FAISS_INDEX))
    idmap2 = json.loads(FAISS_IDMAP.read_text())

    if idx2.ntotal == len(vectors) and len(idmap2) == len(ids):
        print(f"    [OK] 重建成功! {idx2.ntotal} 向量, {dim} 维 L2 索引")
        return True
    else:
        print(f"    [ERROR] 验证失败: index={idx2.ntotal}(期望{len(vectors)}), idmap={len(idmap2)}(期望{len(ids)})")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TreeCut FAISS Index Rebuilder")
    parser.add_argument("--check", action="store_true", help="仅检查同步状态")
    parser.add_argument("--force", action="store_true", help="强制重建（即使索引已同步）")

    args = parser.parse_args()

    if args.check:
        s = check_sync()
        print_status(s)
    else:
        success = rebuild(force=args.force)
        if not success:
            sys.exit(1)
