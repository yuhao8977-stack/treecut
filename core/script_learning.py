"""
树剪 — 脚本学习库 (Script Learning Hub)
================================================================
存储用户投喂的脚本，支持 CRUD、相似检索、使用统计、自学习增强。

数据库表: learned_scripts (位于 ai_material_library.db)
用法:
  from core.script_learning import ScriptLibrary
  lib = ScriptLibrary()
  sid = lib.add_script("岛台装修...", source="manual", tags=["极简风","烤箱"])
  scripts = lib.get_all(limit=20)
  similar = lib.find_similar("岩板岛台...", top_k=5)
"""
import sqlite3
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict


PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "ai_material_library.db"


def _ensure_table():
    """确保 learned_scripts 表和索引存在 (幂等)"""
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
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
        """)
        conn.commit()


class ScriptLibrary:
    """脚本学习库管理器"""

    def __init__(self):
        _ensure_table()
        self._st_model = None

    # ═══════════════════ CRUD ═══════════════════

    def add(self, content: str, source: str = "manual",
            tags: List[str] = None, notes: str = "") -> int:
        """添加脚本并生成 embedding。返回新ID。"""
        tags_str = ",".join(tags) if tags else ""
        embedding_blob = self._encode(content)

        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.execute(
                """INSERT INTO learned_scripts
                   (content, source, tags, embedding, notes)
                   VALUES (?,?,?,?,?)""",
                (content, source, tags_str, embedding_blob, notes)
            )
            conn.commit()
            return cur.lastrowid

    def get_all(self, limit: int = 50, offset: int = 0,
                sort_by: str = "usage_count") -> List[Dict]:
        """分页获取脚本列表"""
        valid = {"usage_count", "avg_score", "created_at", "id"}
        order = sort_by if sort_by in valid else "usage_count"

        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""SELECT id, content, source, tags, usage_count,
                           avg_score, created_at, last_used_at, notes
                    FROM learned_scripts
                    ORDER BY {order} DESC
                    LIMIT ? OFFSET ?""",
                (limit, offset)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_by_id(self, script_id: int) -> Optional[Dict]:
        """获取单条脚本"""
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM learned_scripts WHERE id=?", (script_id,)
            ).fetchone()
            return dict(row) if row else None

    def update(self, script_id: int, content: str = None,
               tags: List[str] = None, notes: str = None):
        """更新脚本内容/标签/备注"""
        with sqlite3.connect(str(DB_PATH)) as conn:
            if content is not None:
                emb = self._encode(content)
                conn.execute(
                    "UPDATE learned_scripts SET content=?, embedding=? WHERE id=?",
                    (content, emb, script_id)
                )
            if tags is not None:
                conn.execute(
                    "UPDATE learned_scripts SET tags=? WHERE id=?",
                    (",".join(tags), script_id)
                )
            if notes is not None:
                conn.execute(
                    "UPDATE learned_scripts SET notes=? WHERE id=?",
                    (notes, script_id)
                )
            conn.commit()

    def update_score(self, script_id: int, score: float):
        """使用后更新评分和使用次数（增量式加权平均）"""
        with sqlite3.connect(str(DB_PATH)) as conn:
            row = conn.execute(
                "SELECT usage_count, avg_score FROM learned_scripts WHERE id=?",
                (script_id,)
            ).fetchone()
            if not row:
                return
            old_n, old_avg = row[0], row[1]
            new_n = old_n + 1
            new_avg = round((old_avg * old_n + score) / new_n, 2)
            conn.execute(
                """UPDATE learned_scripts
                   SET usage_count=?, avg_score=?, last_used_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (new_n, new_avg, script_id)
            )
            conn.commit()

    def delete(self, script_id: int):
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("DELETE FROM learned_scripts WHERE id=?", (script_id,))
            conn.commit()

    def get_count(self) -> int:
        with sqlite3.connect(str(DB_PATH)) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM learned_scripts"
            ).fetchone()[0]

    # ═══════════════════ 检索 ═══════════════════

    def search(self, query: str, limit: int = 20) -> List[Dict]:
        """关键词搜索 (模糊匹配 tags + content)"""
        q = f"%{query}%"
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT id, content, source, tags, usage_count,
                          avg_score, created_at, last_used_at
                   FROM learned_scripts
                   WHERE tags LIKE ? OR content LIKE ?
                   ORDER BY usage_count DESC
                   LIMIT ?""",
                (q, q, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def find_similar(self, content: str, top_k: int = 5) -> List[Dict]:
        """基于向量余弦相似度找最相似的已学习脚本"""
        query_emb = self._encode(content)
        if query_emb is None:
            return []

        import numpy as np
        qv = np.frombuffer(query_emb, dtype=np.float32)

        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, content, tags, usage_count, avg_score, embedding "
                "FROM learned_scripts WHERE embedding IS NOT NULL"
            ).fetchall()

        scored = []
        for r in rows:
            if r["embedding"] is None:
                continue
            try:
                ev = np.frombuffer(r["embedding"], dtype=np.float32)
                sim = float(np.dot(qv, ev) / (
                    np.linalg.norm(qv) * np.linalg.norm(ev) + 1e-8))
                if sim > 0.5:
                    scored.append((sim, dict(r)))
            except Exception:
                continue

        scored.sort(key=lambda x: -x[0])
        return [
            {**s[1], "similarity": round(s[0], 3)}
            for s in scored[:top_k]
        ]

    # ═══════════════════ 批量导入 ═══════════════════

    def import_scripts_from_text(self, raw_text: str, source: str = "import",
                                  force_by_line: bool = False,
                                  skip_duplicates: bool = True) -> Dict:
        """
        智能分割文本并批量导入脚本。

        Returns: {"total": 原始脚本数, "added": 成功新增, "skipped": 重复跳过, "errors": 失败数}
        """
        from core.script_utils import split_scripts
        scripts = split_scripts(raw_text, force_by_line=force_by_line)
        result = {"total": len(scripts), "added": 0, "skipped": 0, "errors": 0, "ids": []}

        if result["total"] == 0:
            result["errors"] = 1
            return result

        for content in scripts:
            if skip_duplicates:
                existing = self._find_exact(content)
                if existing:
                    result["skipped"] += 1
                    continue
            try:
                sid = self.add(content, source=source)
                result["added"] += 1
                result["ids"].append(sid)
            except Exception:
                result["errors"] += 1

        return result

    def _find_exact(self, content: str) -> Optional[int]:
        """查找内容完全一致的脚本ID (去重)"""
        with sqlite3.connect(str(DB_PATH)) as conn:
            row = conn.execute(
                "SELECT id FROM learned_scripts WHERE content=? LIMIT 1",
                (content,)
            ).fetchone()
            return row[0] if row else None

    # ═══════════════════ 多样性选择 ═══════════════════

    def get_script_with_diversity(self, exclude_ids: List[int] = None,
                                   prefer_unused: bool = True) -> Optional[Dict]:
        """选择脚本时优先未使用的（低使用次数），并排除最近N条。"""
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            where = "WHERE 1=1"
            params = []
            if exclude_ids:
                placeholders = ",".join("?" for _ in exclude_ids)
                where += f" AND id NOT IN ({placeholders})"
                params.extend(exclude_ids)
            if prefer_unused:
                query = f"""
                    SELECT * FROM learned_scripts {where}
                    ORDER BY usage_count ASC, RANDOM()
                    LIMIT 1
                """
            else:
                query = f"""
                    SELECT * FROM learned_scripts {where}
                    ORDER BY RANDOM() LIMIT 1
                """
            row = conn.execute(query, params).fetchone()
            return dict(row) if row else None

    # ═══════════════════ 分析 ═══════════════════

    def get_stats(self) -> Dict:
        """获取脚本库统计信息"""
        with sqlite3.connect(str(DB_PATH)) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM learned_scripts").fetchone()[0]
            total_usage = conn.execute(
                "SELECT COALESCE(SUM(usage_count),0) FROM learned_scripts"
            ).fetchone()[0]
            avg_score_all = conn.execute(
                "SELECT COALESCE(AVG(avg_score),0) FROM learned_scripts "
                "WHERE usage_count > 0"
            ).fetchone()[0]
            top_tags = conn.execute(
                "SELECT tags FROM learned_scripts WHERE tags != ''"
            ).fetchall()

        # 统计高频标签
        from collections import Counter
        tag_counter = Counter()
        for (t,) in top_tags:
            for tag in t.split(","):
                tag = tag.strip()
                if tag:
                    tag_counter[tag] += 1

        return {
            "total_scripts": total,
            "total_usage": total_usage,
            "avg_score": round(avg_score_all, 2),
            "top_tags": tag_counter.most_common(10),
        }

    def analyze_patterns(self) -> str:
        """使用 DeepSeek 分析脚本库，提取用户偏好（供自学习引擎调用）"""
        scripts = self.get_all(limit=50, sort_by="usage_count")
        if not scripts:
            return ""

        summary_lines = []
        for s in scripts[:20]:
            preview = s["content"][:60].replace("\n", " ")
            summary_lines.append(
                f"[{s['usage_count']}x, {s['avg_score']:.1f}] {preview}..."
            )

        prompt = (
            "以下是用户最常使用的视频脚本列表（按使用次数排序）。"
            "请分析这些脚本的共同特征: 风格偏好、常用关键词、句长偏好、"
            "情感倾向、CTA模式等。输出3-5条优化建议。\n\n"
            + "\n".join(summary_lines)
        )

        try:
            from core.deepseek_client import get_deepseek
            ds = get_deepseek()
            if ds.available:
                return ds._call(
                    "你是视频脚本分析专家。分析用户脚本偏好并给出优化建议。",
                    prompt, max_tokens=500, temperature=0.5
                ) or ""
        except Exception:
            pass
        return ""

    # ═══════════════════ 内部 ═══════════════════

    def _encode(self, text: str):
        """调用 BGE-M3 生成文本 embedding"""
        try:
            from sentence_transformers import SentenceTransformer
            # 延迟加载
            if self._st_model is None:
                self._st_model = SentenceTransformer("BAAI/bge-m3")
            vec = self._st_model.encode([text])[0]
            import numpy as np
            return np.array(vec, dtype=np.float32).tobytes()
        except Exception:
            return None


# 全局单例
_lib: Optional[ScriptLibrary] = None


def get_library() -> ScriptLibrary:
    global _lib
    if _lib is None:
        _lib = ScriptLibrary()
    return _lib
