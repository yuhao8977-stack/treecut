"""
树剪 — 重试调度器 (RetryScheduler) v1.0
=========================================
质检不合格的视频自动调整参数重试，最多3次后转人工队列。

用法:
    from core.retry_scheduler import get_retry_scheduler
    rs = get_retry_scheduler()
    adjusted = rs.schedule_retry("岛台", original_params, "material_mismatch", 0.45)
    if adjusted:
        pipeline.run(**adjusted)  # 用新参数重试
    else:
        print("已转入人工审核队列")
"""
import sqlite3
import json
import threading
import logging
from pathlib import Path
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

logger = logging.getLogger("RetryScheduler")

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "ai_material_library.db"

MAX_RETRIES = 3


class FailReason(str, Enum):
    """质检不合格原因分类"""
    LOW_SCORE         = "low_score"           # 综合分数低
    MATERIAL_MISMATCH = "material_mismatch"   # 素材不匹配
    TTS_ERROR         = "tts_error"           # 配音问题
    SCRIPT_WEAK       = "script_weak"         # 文案弱
    BGM_WRONG         = "bgm_wrong"           # BGM不合适
    NO_CLIPS_FOUND    = "no_clips_found"      # 无可用素材
    UNKNOWN           = "unknown"


class RetryScheduler:
    """
    质检失败 → 重试调度器。
    最多自动重试3次，每次根据失败原因智能调整参数。
    3次后转 human_review_queue 等待人工处理。
    """

    _instance: Optional["RetryScheduler"] = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._lock = threading.Lock()
                    obj._ensure_tables()
                    cls._instance = obj
        return cls._instance

    def _ensure_tables(self):
        """创建重试相关表"""
        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                conn.executescript("""
                    PRAGMA journal_mode=WAL;

                    CREATE TABLE IF NOT EXISTS retry_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword TEXT NOT NULL,
                        original_params TEXT NOT NULL,
                        adjusted_params TEXT NOT NULL,
                        fail_reason TEXT DEFAULT 'unknown',
                        retry_count INTEGER DEFAULT 0,
                        status TEXT DEFAULT 'pending',
                        last_score REAL DEFAULT 0,
                        error_message TEXT DEFAULT '',
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_retry_status
                        ON retry_queue(status);

                    CREATE TABLE IF NOT EXISTS human_review_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword TEXT NOT NULL,
                        source TEXT DEFAULT 'retry_exhausted',
                        fail_reason TEXT DEFAULT 'unknown',
                        retry_count INTEGER DEFAULT 0,
                        last_score REAL DEFAULT 0,
                        params_snapshot TEXT DEFAULT '{}',
                        notes TEXT DEFAULT '',
                        status TEXT DEFAULT 'pending',
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        resolved_at TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_human_review_status
                        ON human_review_queue(status);
                """)
        except Exception as e:
            logger.error(f"重试相关表创建失败: {e}")

    # ── 调度重试 ────────────────────────────────────────
    def schedule_retry(self, keyword: str, original_params: dict,
                       fail_reason: str, last_score: float = 0,
                       error_message: str = "") -> Optional[dict]:
        """
        调度重试 — 根据失败原因智能调整参数。
        返回: 调整后的参数字典 (可直接传入 pipeline.run()) 或 None (转人工)
        """
        with self._lock:
            with sqlite3.connect(str(DB_PATH)) as conn:
                # 查询当前重试次数
                row = conn.execute(
                    """SELECT id, retry_count FROM retry_queue
                       WHERE keyword=? AND status='pending'
                       ORDER BY id DESC LIMIT 1""",
                    (keyword,)
                ).fetchone()

                retry_count = (row[1] + 1) if row else 1

                # 超过最大重试次数 → 转入人工队列
                if retry_count > MAX_RETRIES:
                    self._enqueue_human(conn, keyword, fail_reason, retry_count,
                                       last_score, original_params)
                    # 标记当前重试为 exhausted
                    if row:
                        conn.execute(
                            "UPDATE retry_queue SET status='exhausted', updated_at=? WHERE id=?",
                            (datetime.now().isoformat(), row[0])
                        )
                    else:
                        conn.execute(
                            """INSERT INTO retry_queue
                               (keyword, original_params, adjusted_params, fail_reason,
                                retry_count, status, last_score, error_message)
                               VALUES (?,?,?,?,?,?,?,?)""",
                            (keyword, json.dumps(original_params), "{}",
                             fail_reason, retry_count, 'exhausted',
                             last_score, error_message)
                        )

                    # 通知UI
                    self._notify_review_pending(keyword)
                    logger.warning(f"重试耗尽: keyword={keyword}, 已转人工队列")
                    return None

                # 调整参数
                adjusted = self._adjust_params(original_params, fail_reason, retry_count)

                # 更新或创建重试记录
                now = datetime.now().isoformat()
                if row:
                    conn.execute(
                        """UPDATE retry_queue
                           SET retry_count=?, adjusted_params=?, fail_reason=?,
                               last_score=?, error_message=?, updated_at=?
                           WHERE id=?""",
                        (retry_count, json.dumps(adjusted, ensure_ascii=False),
                         fail_reason, last_score, error_message, now, row[0])
                    )
                else:
                    conn.execute(
                        """INSERT INTO retry_queue
                           (keyword, original_params, adjusted_params, fail_reason,
                            retry_count, status, last_score, error_message)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (keyword, json.dumps(original_params, ensure_ascii=False),
                         json.dumps(adjusted, ensure_ascii=False),
                         fail_reason, retry_count, 'pending',
                         last_score, error_message)
                    )

                logger.info(f"重试已调度: keyword={keyword}, retry={retry_count}/{MAX_RETRIES}, "
                           f"reason={fail_reason}, score={last_score}")
                return adjusted

    # ── 参数调整策略 ────────────────────────────────────
    def _adjust_params(self, params: dict, fail_reason: str,
                       retry_count: int) -> dict:
        """根据失败原因智能调整生成参数"""
        adjusted = dict(params)
        step = retry_count

        if fail_reason == FailReason.MATERIAL_MISMATCH:
            # 降低匹配阈值，扩大候选池
            adjusted["match_threshold"] = max(0.3,
                params.get("match_threshold", 0.6) - 0.1 * step)
            adjusted["fallback_to_similar"] = True
            adjusted["num_clips"] = min(12,
                params.get("num_clips", 8) + 2 * step)

        elif fail_reason == FailReason.SCRIPT_WEAK:
            # 换文案风格
            styles = ["专业型", "情感型", "对比型", "故事型"]
            adjusted["copy_style"] = styles[step % len(styles)]
            adjusted["force_cta"] = True
            adjusted["expand_keywords"] = True

        elif fail_reason == FailReason.BGM_WRONG:
            # 随机换BGM
            adjusted["bgm_retry"] = step
            adjusted["bgm_mode"] = "random"

        elif fail_reason == FailReason.LOW_SCORE:
            # 综合调整
            adjusted["clip_quality_min"] = max(0.4,
                params.get("clip_quality_min", 0.7) - 0.1 * step)
            adjusted["match_threshold"] = max(0.35,
                params.get("match_threshold", 0.6) - 0.08 * step)
            adjusted["copy_style"] = "情感型"

        elif fail_reason == FailReason.NO_CLIPS_FOUND:
            # 大幅放宽限制
            adjusted["match_threshold"] = max(0.2,
                params.get("match_threshold", 0.6) - 0.15 * step)
            adjusted["fallback_to_similar"] = True
            adjusted["use_fallback_pool"] = True

        elif fail_reason == FailReason.TTS_ERROR:
            # TTS错误 → 降低字数或换引擎
            adjusted["max_chars"] = max(30,
                params.get("max_chars", 80) - 15 * step)
            adjusted["tts_voice"] = "auto"

        # 标记重试信息
        adjusted["_retry_count"] = step
        adjusted["_retry_reason"] = fail_reason
        return adjusted

    # ── 人工队列 ────────────────────────────────────────
    def _enqueue_human(self, conn, keyword: str, fail_reason: str,
                       retry_count: int, last_score: float, params: dict):
        """加入人工审核队列"""
        conn.execute(
            """INSERT INTO human_review_queue
               (keyword, source, fail_reason, retry_count,
                last_score, params_snapshot)
               VALUES (?,?,?,?,?,?)""",
            (keyword, "retry_exhausted", fail_reason, retry_count,
             last_score, json.dumps(params, ensure_ascii=False))
        )

    def resolve_human_review(self, review_id: int, resolved_by: str = "operator",
                              resolution: str = ""):
        """标记人工队列条目为已解决"""
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                """UPDATE human_review_queue
                   SET status='resolved', notes=?,
                       resolved_at=?
                   WHERE id=?""",
                (f"resolved by {resolved_by}: {resolution}",
                 datetime.now().isoformat(), review_id)
            )

    # ── 查询接口 ────────────────────────────────────────
    def get_retry_stats(self) -> dict:
        """获取重试统计"""
        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                total = conn.execute("SELECT COUNT(*) FROM retry_queue").fetchone()[0]
                pending = conn.execute(
                    "SELECT COUNT(*) FROM retry_queue WHERE status='pending'"
                ).fetchone()[0]
                exhausted = conn.execute(
                    "SELECT COUNT(*) FROM retry_queue WHERE status='exhausted'"
                ).fetchone()[0]
                return {"total": total, "pending": pending, "exhausted": exhausted}
        except Exception:
            return {"total": 0, "pending": 0, "exhausted": 0}

    def human_review_count(self) -> int:
        """获取待人工处理的条目数"""
        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM human_review_queue WHERE status='pending'"
                ).fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

    def get_pending_human_reviews(self, limit: int = 20) -> list:
        """获取待人工处理列表"""
        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """SELECT * FROM human_review_queue
                       WHERE status='pending'
                       ORDER BY created_at DESC LIMIT ?""",
                    (limit,)
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def _notify_review_pending(self, keyword: str):
        """通知UI有待审核项"""
        try:
            from core.event_bus import get_bus, Events
            # 只在event_bus可用时发送通知
            get_bus().publish_async(Events.REVIEW_PENDING, {
                "type": "generation_failed",
                "keyword": keyword,
                "human_queue_count": self.human_review_count()
            })
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"事件通知失败(非致命): {e}")

    def clear_stale_retries(self, older_than_hours: int = 72):
        """清理过期重试记录"""
        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                conn.execute(
                    f"""DELETE FROM retry_queue
                        WHERE status IN ('exhausted','pending')
                        AND created_at < datetime('now', '-{older_than_hours} hours')"""
                )
        except Exception as e:
            logger.error(f"清理过期重试记录失败: {e}")


# ── 全局单例访问 ──────────────────────────────────────
def get_retry_scheduler() -> RetryScheduler:
    """获取全局重试调度器单例"""
    return RetryScheduler()
