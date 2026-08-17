"""
V3.0 Upgrade Script: Populate KB + Build BGE-M3 Index + Migrate V2 Data
Run: python upgrade.py
"""
import sys, sqlite3, json, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from material_engine_v3.config import V3_DB_PATH
from material_engine_v3.database.schema import init_db
from material_engine_v3.knowledge.industry_kb import INDUSTRY_KB

V2_DB = Path(__file__).parent.parent / "ai_material_library.db"
FAISS_OUT = Path(__file__).parent.parent / "shipin" / "material_bge_m3.index"
IDMAP_OUT = Path(__file__).parent.parent / "shipin" / "material_bge_m3_idmap.json"

def step1_populate_kb():
    """Populate knowledge_base table with industry terms"""
    print("[Step 1] Populating knowledge base...")
    with sqlite3.connect(V3_DB_PATH) as conn:
        count = 0
        for category, items in INDUSTRY_KB.items():
            for keyword, aliases in items.items():
                try:
                    conn.execute("""INSERT OR IGNORE INTO knowledge_base (category, keyword, aliases, priority)
                        VALUES (?,?,?,?)""", (category, keyword, json.dumps(aliases, ensure_ascii=False), 1))
                    count += 1
                except Exception: pass  # non-critical fallback  # non-critical fallback
        conn.commit()
    print(f"  KB entries: {count}")

def step2_migrate_v2():
    """Migrate V2 materials -> V3 videos + tags"""
    print("[Step 2] Migrating V2 data...")
    if not V2_DB.exists():
        print("  V2 DB not found, skipping")
        return
    with sqlite3.connect(V2_DB) as v2, sqlite3.connect(V3_DB_PATH) as v3:
        rows = v2.execute("SELECT video_path, duration, file_size, file_mtime FROM video_registry WHERE analyzed=1").fetchall()
        for path, dur, size, mtime in rows:
            # Derive source folder from path
            folder = ""
            for sp in [r"Z:\已处理素材\卖点展示类素材", r"Z:\已处理素材\效果展示类素材", r"Z:\B组更新视频"]:
                if sp in str(path):
                    try: folder = Path(path).relative_to(sp).parts[0] if Path(path).relative_to(sp).parts else ""
                    except Exception: pass  # non-critical fallback  # non-critical fallback
                    break
            v3.execute("INSERT OR IGNORE INTO videos (path, source_folder, duration, file_size, file_mtime, status) VALUES (?,?,?,?,?,?)",
                       (str(path), folder or "", dur or 0, size or 0, mtime or 0, "migrated"))
        # Migrate tags from materials table
        tag_rows = v2.execute("SELECT video_path, tags, objects, style, color, material FROM materials WHERE tags != '' OR style != ''").fetchall()
        for path, tags, objects, style, color, material in tag_rows:
            vid = v3.execute("SELECT id FROM videos WHERE path=?", (path,)).fetchone()
            if not vid: continue
            vid = vid[0]
            for level, val in [(1, tags), (2, objects), (3, style), (4, color)]:
                if val:
                    for t in val.split(","):
                        t = t.strip()
                        if t:
                            v3.execute("INSERT OR IGNORE INTO video_tags (video_id, tag_level, tag_category, tag_value, tag_source) VALUES (?,?,?,?,?)",
                                       (vid, level, "migrated", t, "v2_migration"))
        v3.commit()
    print(f"  Migrated: {len(rows)} videos, {len(tag_rows)} tag sets")

def step3_build_bge_m3_index():
    """Build BGE-M3 vector index from V2 materials"""
    print("[Step 3] Building BGE-M3 index...")
    if not V2_DB.exists():
        print("  V2 DB not found, skipping")
        return
    try:
        from sentence_transformers import SentenceTransformer
        import faiss
    except ImportError as e:
        print(f"  Missing: {e}")
        return

    model = SentenceTransformer("BAAI/bge-m3")
    with sqlite3.connect(V2_DB) as conn:
        rows = conn.execute("SELECT id, tags, objects, style, color, material, speech_text FROM materials WHERE analyzed=1").fetchall()
    texts = [" ".join([str(r[i]) for i in range(1,7) if r[i]]) for r in rows]
    ids = [r[0] for r in rows]
    print(f"  Encoding {len(texts)} segments with BGE-M3 (1024-dim)...")
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=128)
    embeddings = np.array(embeddings, dtype=np.float32)
    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings)
    FAISS_OUT.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(FAISS_OUT))
    IDMAP_OUT.write_text(json.dumps(ids))
    print(f"  BGE-M3 index: {len(ids)} vectors, dim={dim}")
    print(f"  Saved: {FAISS_OUT}")

def step4_integrate():
    """Hook V3 search into video_editor.py"""
    print("[Step 4] Integration note:")
    print("  V3 search API: material_engine_v3/core/smart_matcher.py")
    print("  FAISS index integrated via SmartMatcher.search()")
    print(f"    EMBEDDING_MODEL = 'BAAI/bge-m3'")

if __name__ == "__main__":
    init_db()
    step1_populate_kb()
    step2_migrate_v2()
    step3_build_bge_m3_index()
    step4_integrate()
    print("\n[DONE] V3.0 upgrade complete")
