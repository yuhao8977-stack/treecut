# AI Content Factory Platform V3.0

## Architecture Overview

```
material_engine_v3/
├── config.py              Central configuration
├── core/
│   ├── scene_engine.py    Scene detection (PySceneDetect)
│   ├── fusion_engine.py   Multimodal fusion (VL+OCR+Speech+KB)
│   ├── scoring_engine.py  Quality scoring 0-100
│   └── learning_engine.py Auto-learning from corrections
├── knowledge/
│   └── industry_kb.py     Island counter industry KB + VL correction
├── database/
│   ├── schema.py          12-table V3 schema
│   └── material_v3.db     Database
├── api/
│   └── search_api.py      BGE-M3 vector search
├── cache/
│   └── local_cache.py     SQLite cache (Redis-ready)
├── tasks/
│   └── queue.py           Task queue (Celery-ready)
└── logs/                  Log directory
```

## Key Upgrades from V2

| V2 | V3 |
|----|----|
| Fixed 3-frame sampling | PySceneDetect scene detection |
| Single model (Qwen) | Dual model (Qwen + InternVL3 ready) |
| Single-dimension tags | 4-level unified tag system |
| all-MiniLM-L6-v2 | BAAI/bge-m3 (Chinese support) |
| Hard-coded keywords | Industry KB + VL correction |
| No feedback | Auto-learning engine |
| No scoring | 5-dimension quality scoring |
| No task queue | SQLite queue (Celery-ready) |

## Database Tables

- videos, video_scenes, video_frames
- video_tags (4-level), video_embeddings
- video_ocr, video_audio, video_scores
- knowledge_base, custom_tags, feedback_logs
- task_queue

## Usage

```python
# Init
from database.schema import init_db; init_db()

# Scene detection
from core.scene_engine import SceneEngine
engine = SceneEngine()
scenes = engine.detect_scenes("video.mp4")

# Multimodal fusion
from core.fusion_engine import FusionEngine
fusion = FusionEngine()
tags = fusion.fuse(video_id, scene_id, vl_tags, ocr_text, speech_text, filename, folder)

# Search
from api.search_api import SearchEngine
search = SearchEngine()
results = search.search("island counter sintered stone", mode="hybrid")

# Industry KB correction
from knowledge.industry_kb import correct_vl_output
corrected = correct_vl_output("table")  # Returns: "island counter" (Chinese)
```

## Migration from V2

V2 database (ai_material_library.db) can be migrated:
```python
python -c "from database.schema import init_db; init_db()"
# Then run migration script to import from V2 DB
```

## Target Scale

- 100K materials: Current architecture supports
- 500K materials: Add Redis + Celery
- 1M materials: Add PostgreSQL + distributed FAISS
