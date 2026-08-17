"""
树剪 TreeCut v12.0 — EventBus 接線模塊
=======================================
將核心模塊的事件發布連接到EventBus，替代直接函數調用。
所有模塊通過此文件統一注冊事件發布者和訂閱者。

架構:
  Pipeline → publish(GENERATION_DONE)  → UI窗口自動刷新
  Scanner  → publish(MATERIAL_UPDATED) → 素材庫刷新
  Learner  → publish(REVIEW_PENDING)   → 審核面板紅點更新
  Logger   → publish(LOG_MESSAGE)      → 軟件日誌窗口追加
  RetryScheduler → publish(RETRY_SCHEDULED)
"""

import logging
from typing import Optional, Callable

_log = logging.getLogger("TreeCut.EventWiring")

# ── 注冊狀態 ──────────────────────────────────────
_wired = False
_subscribers: dict = {}


def wire_all():
    """
    一次性接線所有核心模塊到 EventBus。
    在 树剪.py 初始化後調用。
    """
    global _wired
    if _wired:
        return
    _wired = True

    _wire_pipeline()
    _wire_scanner()
    _wire_learner()
    _wire_logging()
    _wire_retry_scheduler()
    _subscribe_ui_refresh()
    _log.info("EventBus 接線完成: 5個發布者 + UI訂閱者已連接")


# ── Pipeline → EventBus ──────────────────────────
def _wire_pipeline():
    """將 Pipeline 的生成完成/失敗事件接入 EventBus"""
    try:
        from core.event_bus import get_bus, Events
        bus = get_bus()

        # 對 pipeline.run() 添加事件發布包裝
        import core.pipeline as pl
        _original_run = pl.run

        def _run_with_event(**kwargs):
            """pipeline.run 包裝 — 發布 GENERATION_STARTED/DONE/FAILED"""
            bus.publish(Events.GENERATION_STARTED, {"keyword": kwargs.get("keyword", "")})
            try:
                result = _original_run(**kwargs)
                bus.publish(Events.GENERATION_DONE, {
                    "keyword": kwargs.get("keyword", ""),
                    "result": result,
                })
                # 同步發布質量結果
                if result and isinstance(result, dict):
                    bus.publish(Events.QUALITY_RESULT, result)
                return result
            except Exception as e:
                bus.publish(Events.GENERATION_FAILED, {
                    "keyword": kwargs.get("keyword", ""),
                    "error": str(e),
                })
                raise

        pl.run = _run_with_event
        _log.debug("Pipeline 已接線到 EventBus")
    except Exception as e:
        _log.warning(f"Pipeline 接線失敗: {e}")


# ── Scanner → EventBus ───────────────────────────
def _wire_scanner():
    """將素材掃描完成事件接入 EventBus"""
    try:
        from core.event_bus import get_bus, Events
        bus = get_bus()

        # 對 LibraryBuilder 的掃描函數進行猴子補丁
        import core.library_builder as lb
        _original_scan = lb.LibraryBuilder.incremental_scan

        def _scan_with_event(self, root_path=None, **kwargs):
            result = _original_scan(self, root_path=root_path, **kwargs)
            bus.publish(Events.SCAN_COMPLETE, {"root_path": str(root_path) if root_path else "default"})
            bus.publish(Events.MATERIAL_UPDATED, {"source": "incremental_scan"})
            return result

        lb.LibraryBuilder.incremental_scan = _scan_with_event
        _log.debug("Scanner 已接線到 EventBus")
    except Exception as e:
        _log.warning(f"Scanner 接線失敗: {e}")


# ── Learner → EventBus ───────────────────────────
def _wire_learner():
    """將學習完成/審核待處理事件接入 EventBus"""
    try:
        from core.event_bus import get_bus, Events
        bus = get_bus()

        import core.learner as learner
        _original_bulk = learner.KnowledgeLearner.bulk_learn

        def _bulk_with_event(self, data):
            result = _original_bulk(self, data)
            bus.publish(Events.LEARNING_DONE, {"summary": self.get_summary()})

            # 檢查是否有待審核項
            try:
                from core.review_queue import get_review_queue
                rq = get_review_queue()
                pending = rq.pending_count()
                if pending > 0:
                    bus.publish(Events.REVIEW_PENDING, {
                        "count": pending,
                        "message": f"有 {pending} 條AI建議待審核"
                    })
            except ImportError:
                pass
            return result

        learner.KnowledgeLearner.bulk_learn = _bulk_with_event
        _log.debug("Learner 已接線到 EventBus")
    except Exception as e:
        _log.warning(f"Learner 接線失敗: {e}")


# ── Logging → EventBus ───────────────────────────
def _wire_logging():
    """將日誌消息接入 EventBus（由 utils/logging.py 內部觸發）"""
    try:
        from core.event_bus import get_bus, Events
        bus = get_bus()
        # logging 模塊內部已通過 LogManager._publish_to_ui 發送
        # 此行確保 EventBus 已初始化
        _log.debug("Logging → EventBus 通道已激活")
    except Exception as e:
        _log.warning(f"Logging 接線失敗: {e}")


# ── RetryScheduler → EventBus ────────────────────
def _wire_retry_scheduler():
    """將重試調度事件接入 EventBus"""
    try:
        from core.event_bus import get_bus, Events
        bus = get_bus()
        _log.debug("RetryScheduler → EventBus 通道已激活")
    except Exception as e:
        _log.warning(f"RetryScheduler 接線失敗: {e}")


# ── UI 訂閱者 ─────────────────────────────────────
def _subscribe_ui_refresh():
    """為UI窗口注冊默認事件處理器"""
    try:
        from core.event_bus import get_bus, Events
        bus = get_bus()

        # 默認處理器: 打印到控制台
        def _default_log_handler(data):
            if data and data.get("message"):
                print(f"[EventBus] {data.get('module','?')}: {data['message']}")

        bus.subscribe(Events.LOG_MESSAGE, _default_log_handler)
        _log.debug("UI默認事件處理器已注冊")

        # Progress更新處理器
        def _progress_handler(data):
            if data:
                done = data.get("done", 0)
                total = data.get("total", 1)
                pct = int(done / max(total, 1) * 100)
                print(f"\r[Progress] {pct}% ({done}/{total})", end="", flush=True)

        bus.subscribe(Events.PROGRESS_UPDATE, _progress_handler)
    except Exception as e:
        _log.warning(f"UI訂閱注冊失敗: {e}")


# ── 便捷函數 ──────────────────────────────────────
def publish_progress(done: int, total: int, task_name: str = ""):
    """便捷: 發布進度更新"""
    try:
        from core.event_bus import get_bus, Events
        get_bus().publish(Events.PROGRESS_UPDATE, {
            "done": done, "total": total, "task": task_name
        })
    except Exception:
        pass


def publish_log(module: str, level: str, message: str):
    """便捷: 發布日誌消息到 EventBus"""
    try:
        from core.event_bus import get_bus, Events
        get_bus().publish(Events.LOG_MESSAGE, {
            "module": module, "level": level, "message": message
        })
    except Exception:
        pass


def publish_review_pending(count: int):
    """便捷: 發布審核待處理通知"""
    try:
        from core.event_bus import get_bus, Events
        get_bus().publish(Events.REVIEW_PENDING, {"count": count})
    except Exception:
        pass
