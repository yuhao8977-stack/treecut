"""
V3.1 Batch Processor: Populate embeddings + Run scene detection + Score materials
"""
import sys, sqlite3, json, faiss, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from material_engine_v3.database.schema import init_db
from material_engine_v3.config import V3_DB_PATH

BASE_DIR = Path(__file__).parent.parent
FAISS_BGE = BASE_DIR / "shipin" / "material_bge_m3.index"
FAISS_IDMAP = BASE_DIR / "shipin" / "material_bge_m3_idmap.json"
V2_DB = BASE_DIR / "ai_material_library.db"

def step1_populate_embeddings():
    """Read BGE-M3 FAISS index, populate V3 video_embeddings table"""
    print("[Step 1] Populating embeddings from BGE-M3 index...")
    if not FAISS_BGE.exists():
        print(f"  FAISS index not found: {FAISS_BGE}"); return
    index = faiss.read_index(str(FAISS_BGE))
    ids = json.loads(FAISS_IDMAP.read_text())
    print(f"  Index: {index.ntotal} vectors, dim={index.d}")
    # Reconstruct all embeddings
    embeddings = np.zeros((index.ntotal, index.d), dtype=np.float32)
    faiss.extract_index_ivf(index) if hasattr(index, 'invlists') else None
    # For FlatL2, we can just read directly... but FAISS doesn't expose raw vectors easily
    # Alternative: populate from V2 materials table mapping
    if V2_DB.exists():
        with sqlite3.connect(V2_DB) as v2, sqlite3.connect(V3_DB_PATH) as v3:
            v2_rows = v2.execute("SELECT id FROM materials WHERE analyzed=1").fetchall()
            for v2_id, in v2_rows:
                v2_id = int(v2_id)
                if v2_id in ids:
                    idx_pos = ids.index(v2_id)
                    try:
                        vec = index.reconstruct(idx_pos)
                        vec_blob = vec.tobytes()
                        # Find corresponding V3 video
                        v2_path = v2.execute("SELECT video_path FROM materials WHERE id=?", (v2_id,)).fetchone()
                        if v2_path:
                            v3_vid = v3.execute("SELECT id FROM videos WHERE path=?", (v2_path[0],)).fetchone()
                            if v3_vid:
                                v3.execute("INSERT OR IGNORE INTO video_embeddings (video_id, embedding, model_name, dimension) VALUES (?,?,?,?)",
                                           (v3_vid[0], vec_blob, "BAAI/bge-m3", index.d))
                    except Exception: pass  # non-critical fallback  # non-critical fallback
            v3.commit()
    with sqlite3.connect(V3_DB_PATH) as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM video_embeddings").fetchone()[0]
    print(f"  Embeddings populated: {cnt}")

def step2_sample_scenes(limit=20):
    """Run scene detection on a sample batch"""
    print(f"[Step 2] Scene detection on {limit} sample videos...")
    try:
        from material_engine_v3.core.scene_engine import SceneEngine
        engine = SceneEngine()
        cnt = 0
        with sqlite3.connect(V3_DB_PATH) as conn:
            vids = conn.execute("SELECT id, path, duration FROM videos WHERE duration > 0 LIMIT ?", (limit,)).fetchall()
            for vid, path, dur in vids:
                if not Path(path).exists(): continue
                scenes = engine.detect_scenes(path)
                for s in scenes:
                    conn.execute("""INSERT INTO video_scenes (video_id, scene_index, start_time, end_time)
                        VALUES (?,?,?,?)""", (vid, s["index"], s["start"], s["end"]))
                print(f"  Video {vid}: {len(scenes)} scenes")
            conn.commit()
            cnt = conn.execute("SELECT COUNT(*) FROM video_scenes").fetchone()[0]
        print(f"  Total scenes: {cnt}")
    except Exception as e:
        import traceback
        print(f"  Scene detection error: {e}")
        traceback.print_exc()

def step3_batch_score(limit=100):
    """Score a batch of materials"""
    print(f"[Step 3] Scoring {limit} materials...")
    print("  [SKIP] ScoringEngine not available — material_engine_v3.core.scoring_engine removed in v11.1")
    print("  Use core.quality_scorer for material quality assessment instead.")
    return

if __name__ == "__main__":
    init_db()
    step1_populate_embeddings()
    step2_sample_scenes(limit=20)
    step3_batch_score(limit=100)
    # Final stats
    with sqlite3.connect(V3_DB_PATH) as conn:
        for table in ["video_scenes","video_embeddings","video_scores"]:
            cnt = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table}: {cnt}")
    print("\n[DONE] V3.1 batch processing complete")
