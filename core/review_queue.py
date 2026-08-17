"""
树剪 — AI审核队列 (ReviewQueue) v1.0
=====================================
★ 安全改造核心: 替代 self_evolver 的 _apply_fixes 直写逻辑
   AI只能生成JSON规则建议，所有建议必须经人工审核后才可应用。

用法:
    from core.review_queue import get_review_queue
    rq = get_review_queue()
    rid = rq.submit("标签优化", rule_dict, "DeepSeek", 0.8)
    # ... 人工审核 ...
    rq.approve(rid, reviewer="操作员")
"""
import sqlite3
import json
import threading
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger("ReviewQueue")

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "ai_material_library.db"

# ★ 安全: AI规则JSON Schema — 不允许包含代码/危险内容
ALLOWED_RULE_KEYS: Dict[str, Optional[List[str]]] = {
    "copywriting":      ["hooks", "selling_phrases", "cta_templates", "industry_terms", "tone_words"],
    "protected_words":  ["product_names", "material_terms", "craft_terms", "style_terms", "brand_terms"],
    "knowledge_base":   ["stone_variants", "craft_techniques", "hardware_items", "style_variants", "color_names"],
    "keyword_mapping":  None,   # 允许任意key
    "synonyms":         None,   # 允许任意key
    "script_patterns":  ["openings", "transitions", "closings"],
}

DANGEROUS_KEYWORDS = {"exec", "eval", "import", "subprocess", "__", "code", "script",
                       "os.", "sys.", "compile", "execfile", "open(", "write(", "delete("}


def _validate_rule_schema(rule: dict) -> Tuple[bool, str]:
    """
    验证规则JSON格式和安全性。
    拒绝: 包含代码执行关键词、非字符串值、过长词条、未知类型。
    返回: (是否合法, 错误信息)
    """
    if not isinstance(rule, dict):
        return False, "规则必须是字典"

    # 检查危险关键词
    rule_str = json.dumps(rule, ensure_ascii=False).lower()
    for dk in DANGEROUS_KEYWORDS:
        if dk in rule_str:
            return False, f"规则包含危险关键词: {dk}"

    # 检查rule_type级别
    for section, cats in rule.items():
        if section not in ALLOWED_RULE_KEYS:
            return False, f"未知规则类型: {section}"

        if not isinstance(rule[section], dict):
            return False, f"{section} 必须是字典"

        allowed_cats = ALLOWED_RULE_KEYS[section]
        if allowed_cats is not None:  # 有限制的section
            for cat in rule[section]:
                if cat not in allowed_cats:
                    return False, f"不允许的子类别: {section}.{cat}"
                items = rule[section][cat]
                if not isinstance(items, list):
                    return False, f"{section}.{cat} 必须是列表"
                for item in items:
                    if not isinstance(item, str):
                        return False, f"{section}.{cat} 列表只能包含纯文本字符串"
                    if len(item) > 100:
                        return False, f"词条过长(>100字符): {item[:30]}..."

    return True, "OK"


class ReviewQueue:
    """
    AI建议审核队列 — 所有AI生成的内容必须经人工确认后方可应用。
    替代 self_evolver._apply_fixes 的代码直写行为。
    """

    _instance: Optional["ReviewQueue"] = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._lock = threading.Lock()
                    obj._ensure_table()
                    cls._instance = obj
        return cls._instance

    def _ensure_table(self):
        """创建审核队列表"""
        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                conn.executescript("""
                    PRAGMA journal_mode=WAL;

                    CREATE TABLE IF NOT EXISTS ai_review_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        rule_type TEXT NOT NULL,
                        content TEXT NOT NULL,
                        source TEXT DEFAULT 'AI',
                        confidence REAL DEFAULT 0.0,
                        status TEXT DEFAULT 'pending',
                        reviewer TEXT DEFAULT '',
                        review_note TEXT DEFAULT '',
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        reviewed_at TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_review_status
                        ON ai_review_queue(status);
                """)
        except Exception as e:
            logger.error(f"审核队列表创建失败: {e}")

    # ── 提交审核 ────────────────────────────────────────
    def submit(self, rule_type: str, content: dict, source: str = "AI",
               confidence: float = 0.0) -> int:
        """
        提交AI建议到审核队列。
        返回: review_id (int)，可用于后续 approve/reject。
        """
        # 安全验证
        valid, msg = _validate_rule_schema(content)
        if not valid:
            logger.warning(f"规则schema验证失败, 拒绝提交: {msg}")
            raise ValueError(f"规则验证失败: {msg}")

        with sqlite3.connect(str(DB_PATH)) as conn:
            cur = conn.execute(
                """INSERT INTO ai_review_queue
                   (rule_type, content, source, confidence)
                   VALUES (?,?,?,?)""",
                (rule_type, json.dumps(content, ensure_ascii=False), source, confidence)
            )
            rid = cur.lastrowid
            logger.info(f"AI建议已提交审核: id={rid}, type={rule_type}, source={source}")
            return rid

    # ── 审核通过 ────────────────────────────────────────
    def approve(self, review_id: int, reviewer: str = "human") -> bool:
        """
        审核通过 — 自动应用规则到 learner。
        返回: True=成功应用, False=审核ID不存在或规则无效。
        """
        with sqlite3.connect(str(DB_PATH)) as conn:
            row = conn.execute(
                """SELECT rule_type, content FROM ai_review_queue
                   WHERE id=? AND status='pending'""",
                (review_id,)
            ).fetchone()

            if not row:
                logger.warning(f"审核ID不存在或已处理: {review_id}")
                return False

            rule_type, content_str = row
            try:
                content = json.loads(content_str)
            except json.JSONDecodeError:
                logger.error(f"审核队列中的规则JSON损坏: id={review_id}")
                conn.execute(
                    "UPDATE ai_review_queue SET status='corrupted', review_note=? WHERE id=?",
                    ("JSON解析失败", review_id)
                )
                return False

            # 再次验证安全性（防止数据库被篡改）
            valid, msg = _validate_rule_schema(content)
            if not valid:
                logger.warning(f"审核拒绝: {msg}")
                conn.execute(
                    "UPDATE ai_review_queue SET status='rejected', review_note=? WHERE id=?",
                    (f"安全检查失败: {msg}", review_id)
                )
                return False

            # 应用规则到 learner
            try:
                from core.learner import get_learner
                get_learner().bulk_learn(content)
                logger.info(f"规则已应用: id={review_id}, type={rule_type}")
            except Exception as e:
                logger.error(f"规则应用失败: {e}")
                conn.execute(
                    "UPDATE ai_review_queue SET status='apply_failed', review_note=? WHERE id=?",
                    (str(e)[:200], review_id)
                )
                return False

            # 标记已通过
            conn.execute(
                """UPDATE ai_review_queue
                   SET status='approved', reviewer=?, reviewed_at=?
                   WHERE id=?""",
                (reviewer, datetime.now().isoformat(), review_id)
            )
            return True

    # ── 审核拒绝 ────────────────────────────────────────
    def reject(self, review_id: int, note: str = ""):
        """审核拒绝 — 标记规则为已拒绝"""
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                """UPDATE ai_review_queue
                   SET status='rejected', review_note=?, reviewed_at=?
                   WHERE id=? AND status='pending'""",
                (note[:500], datetime.now().isoformat(), review_id)
            )
            logger.info(f"规则已拒绝: id={review_id}, note={note[:100]}")

    # ── 查询 ────────────────────────────────────────────
    def pending_count(self) -> int:
        """获取待审核数量"""
        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM ai_review_queue WHERE status='pending'"
                ).fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

    def get_pending(self, limit: int = 20) -> List[dict]:
        """获取待审核列表"""
        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """SELECT id, rule_type, content, source,
                              confidence, created_at
                       FROM ai_review_queue
                       WHERE status='pending'
                       ORDER BY created_at DESC LIMIT ?""",
                    (limit,)
                ).fetchall()
                result = []
                for r in rows:
                    d = dict(r)
                    try:
                        d["content"] = json.loads(d["content"])
                    except json.JSONDecodeError:
                        d["content"] = {"_error": "JSON解析失败"}
                    result.append(d)
                return result
        except Exception as e:
            logger.error(f"获取待审核列表失败: {e}")
            return []

    def get_history(self, limit: int = 50, status: str = None) -> List[dict]:
        """获取审核历史"""
        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                conn.row_factory = sqlite3.Row
                if status:
                    rows = conn.execute(
                        """SELECT * FROM ai_review_queue
                           WHERE status=?
                           ORDER BY created_at DESC LIMIT ?""",
                        (status, limit)
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM ai_review_queue ORDER BY created_at DESC LIMIT ?",
                        (limit,)
                    ).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"获取审核历史失败: {e}")
            return []

    def get_stats(self) -> dict:
        """获取审核队列统计"""
        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                total = conn.execute(
                    "SELECT COUNT(*) FROM ai_review_queue"
                ).fetchone()[0]
                pending = conn.execute(
                    "SELECT COUNT(*) FROM ai_review_queue WHERE status='pending'"
                ).fetchone()[0]
                approved = conn.execute(
                    "SELECT COUNT(*) FROM ai_review_queue WHERE status='approved'"
                ).fetchone()[0]
                rejected = conn.execute(
                    "SELECT COUNT(*) FROM ai_review_queue WHERE status='rejected'"
                ).fetchone()[0]
                return {
                    "total": total, "pending": pending,
                    "approved": approved, "rejected": rejected
                }
        except Exception:
            return {"total": 0, "pending": 0, "approved": 0, "rejected": 0}


# ── 全局单例访问 ──────────────────────────────────────
def get_review_queue() -> ReviewQueue:
    """获取全局审核队列单例"""
    return ReviewQueue()
