"""
V3.5 智能匹配引擎 — 向量检索 + 知识库规则降级
替换原有的 search_by_text, 支持配置开关
"""
import sqlite3, json, os, time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

# ── v12.2: 路径修正 (从 material_engine_v3/core/ 迁移到 core/) ──
_PROJ = Path(__file__).parent.parent  # 项目根目录
DB_PATH = str(_PROJ / "ai_material_library.db")
USE_VECTOR_SEARCH = os.environ.get("TREECUT_USE_VECTOR_SEARCH", "True").lower() == "true"
USE_KNOWLEDGE_FALLBACK = True


class SmartMatcher:
    """智能匹配 — 向量优先, 知识库降级"""

    def __init__(self):
        self._kb = None
        self._faiss_index = None
        self._id_map = []
        self._loaded = False
        self._st_model = None  # 缓存的SentenceTransformer实例

    def _lazy_load(self):
        if self._loaded: return
        # Try loading FAISS — use temp ASCII dir if Chinese path fails
        faiss_path = _PROJ / "shipin" / "material_faiss.index"
        idmap_path = _PROJ / "shipin" / "material_faiss_idmap.json"
        if USE_VECTOR_SEARCH and faiss_path.exists() and idmap_path.exists():
            try:
                import faiss
                import tempfile
                import shutil
                _tmp = tempfile.mkdtemp(prefix="faiss_sm_")
                try:
                    _tmp_idx = os.path.join(_tmp, "material_faiss.index")
                    _tmp_map = os.path.join(_tmp, "material_faiss_idmap.json")
                    shutil.copy2(str(faiss_path), _tmp_idx)
                    shutil.copy2(str(idmap_path), _tmp_map)
                    self._faiss_index = faiss.read_index(_tmp_idx)
                    with open(_tmp_map, encoding="utf-8") as _fm: self._id_map = json.load(_fm)
                finally:
                    shutil.rmtree(_tmp, ignore_errors=True)
            except Exception as e:
                print(f"   [WARN] FAISS load failed (non-critical): {e}")
        # Load knowledge bridge
        try:
            from utils.knowledge import KnowledgeBridge
            self._kb = KnowledgeBridge()
        except Exception as e:
            print(f"   [WARN] KnowledgeBridge load failed (non-critical): {e}")
        self._loaded = True  # Mark loaded even on partial failure — layers will degrade gracefully

    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        """智能搜索 — Layer1:向量 / Layer2:知识库 / Layer3:SQL关键词"""
        self._lazy_load()

        # Use main materials DB for all searches
        main_db = str(_PROJ / "ai_material_library.db")

        # Layer 1: FAISS 向量检索
        if self._faiss_index and self._id_map:
            try:
                import numpy as np
                if self._st_model is None:
                    from sentence_transformers import SentenceTransformer
                    self._st_model = SentenceTransformer("BAAI/bge-m3")
                vec = np.array(self._st_model.encode([query]), dtype=np.float32)
                # Handle BGE-M3 dimension change: 768 (old) vs 1024 (new)
                faiss_dim = self._faiss_index.d
                if vec.shape[1] != faiss_dim:
                    # Truncate to match FAISS dimension (first N dims of BGE-M3 are most significant)
                    vec = vec[:, :faiss_dim]
                dists, indices = self._faiss_index.search(vec, min(top_k * 2, len(self._id_map)))
                results = []
                with sqlite3.connect(main_db) as conn:
                    for i, d in zip(indices[0], dists[0]):
                        if 0 <= i < len(self._id_map):
                            row = conn.execute(
                                "SELECT video_path, start_time, end_time, tags, objects, style, color, material, blocked, has_human FROM materials WHERE id=?",
                                (self._id_map[i],)
                            ).fetchone()
                            if row:
                                # Skip blocked materials (v11.2 feedback learning)
                                if len(row) > 9 and (row[8] == 1 or row[9] == 1):
                                    continue  # blocked=1 or has_human=1
                                results.append(dict(zip(["video_path","start_time","end_time","tags","objects","style","color","material"], row)))
                                results[-1]["score"] = round(1.0/(1.0+float(d)), 3)
                                results[-1]["match_method"] = "FAISS向量"
                # v11.2: Adjust by feedback score
                results = self._adjust_by_feedback(results)
                if results: return results[:top_k]
            except Exception as e:
                print(f"   !! FAISS检索失败: {e}")

        # Layer 2: 知识库规则匹配
        if USE_KNOWLEDGE_FALLBACK and self._kb:
            try:
                kws = self._kb.extract_copy_keywords(query)
                kw_list = []
                for items in kws.values(): kw_list.extend(items)
                if kw_list:
                    kw_str = "%".join(kw_list[:10])
                    with sqlite3.connect(main_db) as conn:
                        rows = conn.execute(
                            "SELECT video_path, start_time, end_time, tags, objects, style, color, material FROM materials WHERE blocked=0 AND has_human=0 AND (tags LIKE ? OR objects LIKE ?) LIMIT ?",
                            (f"%{kw_str}%", f"%{kw_str}%", top_k)
                        ).fetchall()
                    results = [dict(zip(["video_path","start_time","end_time","tags","objects","style","color","material"], r), score=0.7, match_method="知识库规则") for r in rows]
                    results = self._adjust_by_feedback(results)
                    if results: return results
            except Exception as e:
                print(f"   [WARN] Knowledge layer search failed: {e}")

        # Layer 3: SQL关键词降级
        kw = query.replace(" ", "%")
        with sqlite3.connect(main_db) as conn:
            rows = conn.execute(
                "SELECT video_path, start_time, end_time, tags, objects, style, color, material FROM materials WHERE blocked=0 AND has_human=0 AND (tags LIKE ? OR objects LIKE ?) LIMIT ?",
                (f"%{kw}%", f"%{kw}%", top_k)
            ).fetchall()
        results = [dict(zip(["video_path","start_time","end_time","tags","objects","style","color","material"], r), score=0.5, match_method="SQL关键词") for r in rows]
        results = self._adjust_by_feedback(results)
        return results

    def _adjust_by_feedback(self, results: List[Dict]) -> List[Dict]:
        """v11.2: 根据用户反馈动态调整素材得分。
        公式: new_score = min(1.0, original_score * (0.7 + avg_rating/10.0))
        """
        if not results:
            return results
        try:
            main_db = str(_PROJ / "ai_material_library.db")
            if not os.path.exists(main_db):
                return results

            # ★ v12.2优化: 批量查询替代循环中的N次独立查询
            paths = [str(r.get("video_path", "")) for r in results if r.get("video_path")]
            if not paths:
                return results

            with sqlite3.connect(main_db) as conn:
                placeholders = ','.join(['?'] * len(paths))
                rows = conn.execute(
                    f"SELECT material_path, AVG(rating), COUNT(*) FROM material_feedback WHERE material_path IN ({placeholders}) GROUP BY material_path",
                    paths
                ).fetchall()
                # 构建路径→评分的快速查找表
                feedback_map = {}
                for row in rows:
                    if row[0] and row[1] is not None and row[2] > 0:
                        feedback_map[row[0]] = float(row[1])

            # 使用批量查询结果一次性调整
            for r in results:
                path = r.get("video_path", "")
                if path and str(path) in feedback_map:
                    avg_rating = feedback_map[str(path)]
                    factor = 0.7 + avg_rating / 10.0
                    original = float(r.get("score", 0.5))
                    r["score"] = round(min(1.0, original * factor), 3)
                    r["match_method"] = r.get("match_method", "") + "+反馈调整"
        except Exception:
            pass  # 反馈调整失败不阻塞搜索
        return results

    def search_by_copy(self, copy_text: str, num_clips: int = 8) -> List[Dict]:
        import re
        sentences = [s.strip() for s in re.split(r'[。！？]', copy_text) if len(s.strip()) >= 4]
        clips = []; used = set()
        for sent in sentences[:num_clips]:
            results = self.search(sent, top_k=5)
            for r in results:
                cid = f"{r.get('video_path','')}:{r.get('start_time',0)}"
                if cid not in used: clips.append(r); used.add(cid); break
        return clips

    def search_by_visual_requirements(self, parsed_script: Dict,
                                       num_clips: int = 8) -> List[Dict]:
        """
        基于脚本语义解析结果进行智能检索 (v11 新增)。

        parsed_script 格式:
          {"segments": [{visual_requirements: {scene,objects,actions,style,materials,colors,emotion}}], ...}

        策略:
        1. 将每个 segment 的 visual_requirements 转为加权查询文本
        2. FAISS 向量检索 → 知识库规则 → SQL 三层
        3. 返回去重后的片段列表，附带匹配方法
        """
        self._lazy_load()
        main_db = str(_PROJ / "ai_material_library.db")
        all_clips = []
        used_ids = set()

        for seg in parsed_script.get("segments", []):
            req = seg.get("visual_requirements", {})

            # 构建加权查询字符串: 材质和风格权重更高
            parts = []
            for cat, weight in [("materials", 3), ("style", 3), ("objects", 2),
                                 ("scene", 2), ("colors", 1), ("actions", 1)]:
                items = req.get(cat, [])
                parts.extend(items * weight)

            query = " ".join(parts) if parts else seg.get("text", "")

            # FAISS 向量
            if self._faiss_index and self._id_map and query.strip():
                try:
                    import numpy as np
                    if self._st_model is None:
                        from sentence_transformers import SentenceTransformer
                        self._st_model = SentenceTransformer("BAAI/bge-m3")
                    vec = np.array(self._st_model.encode([query]), dtype=np.float32)
                    if vec.shape[1] != self._faiss_index.d:
                        vec = vec[:, :self._faiss_index.d]
                    dists, indices = self._faiss_index.search(vec, 3)
                    with sqlite3.connect(main_db) as conn:
                        for i, d in zip(indices[0], dists[0]):
                            if 0 <= i < len(self._id_map) and i not in used_ids:
                                row = conn.execute(
                                    "SELECT video_path,start_time,end_time,tags,objects,style,color,material,blocked,has_human FROM materials WHERE id=?",
                                    (self._id_map[i],)
                                ).fetchone()
                                if row:
                                    # Skip blocked materials (v11.2)
                                    if len(row) > 9 and (row[8] == 1 or row[9] == 1):
                                        continue  # blocked=1 or has_human=1
                                    clip = dict(zip(
                                        ["video_path","start_time","end_time",
                                         "tags","objects","style","color","material"], row))
                                    clip["score"] = round(1.0/(1.0+float(d)), 3)
                                    clip["match_method"] = "FAISS语义向量"
                                    all_clips.append(clip)
                                    used_ids.add(i)
                except Exception as e:
                    print(f"   [SmartMatcher] 语义检索失败: {e}")

            # SQL 知识库降级
            if len(all_clips) < num_clips and query.strip():
                try:
                    kw_str = "%".join(query.split()[:8])
                    with sqlite3.connect(main_db) as conn:
                        rows = conn.execute(
                            "SELECT video_path,start_time,end_time,tags,objects,style,color,material FROM materials WHERE blocked=0 AND has_human=0 AND (tags LIKE ? OR objects LIKE ?) LIMIT ?",
                            (f"%{kw_str}%", f"%{kw_str}%", num_clips - len(all_clips) + 2)
                        ).fetchall()
                    for r in rows:
                        clip = dict(zip(
                            ["video_path","start_time","end_time",
                             "tags","objects","style","color","material"], r))
                        cid = f"{clip['video_path']}:{clip['start_time']}"
                        if cid not in used_ids:
                            clip["score"] = 0.6
                            clip["match_method"] = "知识库规则"
                            all_clips.append(clip)
                            used_ids.add(cid)
                except Exception:
                    pass

        # v11.2: Apply feedback weight adjustment
        all_clips = self._adjust_by_feedback(all_clips)
        return sorted(all_clips, key=lambda x: -x.get("score", 0))[:num_clips]


# 全局单例
_matcher = None
def get_smart_matcher(): global _matcher; _matcher = _matcher or SmartMatcher(); return _matcher
