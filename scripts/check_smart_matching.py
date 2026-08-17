#!/usr/bin/env python3
"""智能匹配诊断脚本 - 检查 FAISS、知识库、分析状态是否就绪"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def main():
    print("=" * 60)
    print("  树剪智能匹配诊断工具")
    print("=" * 60)

    import sqlite3
    db = Path("ai_material_library.db")
    if not db.exists():
        print("[FAIL] ai_material_library.db 不存在")
        return
    conn = sqlite3.connect(str(db))
    total = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
    analyzed = conn.execute("SELECT COUNT(*) FROM materials WHERE analyzed=1").fetchone()[0]
    embed = conn.execute("SELECT COUNT(*) FROM materials WHERE embedding IS NOT NULL").fetchone()[0]
    tags = conn.execute("SELECT COUNT(*) FROM materials WHERE tags != ''").fetchone()[0]
    print(f"[INFO] 素材片段: {total:,}, 已分析: {analyzed:,}, 有标签: {tags:,}, 有 embedding: {embed:,}")

    faiss_path = Path("shipin/material_faiss.index")
    if faiss_path.exists():
        try:
            import faiss
            idx = faiss.read_index(str(faiss_path))
            size_mb = faiss_path.stat().st_size / 1e6
            print(f"[OK] FAISS 索引存在, 向量数: {idx.ntotal}, 维度: {idx.d}, 大小: {size_mb:.1f}MB")
        except Exception as e:
            print(f"[FAIL] FAISS 索引读取失败: {e}")
    else:
        print("[FAIL] FAISS 索引不存在，请运行: python force_rebuild_faiss.py")

    from utils.knowledge import get_bridge
    kb = get_bridge()
    test_kws = kb.extract_copy_keywords("岩板岛台极简风")
    total_kw = sum(len(v) for v in test_kws.values())
    if total_kw >= 2:
        print(f"[OK] 知识库正常, 提取 {total_kw} 个关键词: {dict((k,list(v)[:3]) for k,v in test_kws.items() if v)}")
    else:
        print(f"[FAIL] 知识库提取关键词不足 (仅 {total_kw} 个)")

    try:
        from material_engine_v3.core.smart_matcher import SmartMatcher
        matcher = SmartMatcher()
        results = matcher.search("极简风岩板岛台", top_k=3)
        if results:
            methods = set(r.get("match_method", "?") for r in results)
            print(f"[OK] 智能匹配返回 {len(results)} 个结果, 方法: {methods}")
            for r in results[:2]:
                name = Path(r["video_path"]).name if r.get("video_path") else "?"
                print(f"    - {name} [{r.get('match_method','?')}] score={r.get('score',0):.3f}")
        else:
            print("[FAIL] 智能匹配无结果，请检查 FAISS 索引或素材分析状态")
    except Exception as e:
        print(f"[FAIL] 智能匹配异常: {e}")

    conn.close()
    print("=" * 60)

if __name__ == "__main__":
    main()
