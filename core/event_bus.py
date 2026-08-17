"""
树剪 — 统一事件总线 (EventBus) v2.0
====================================
替代各模块直接调用 UI after()，实现解耦的发布-订阅模式。
所有线程安全，支持同步/异步发布。
"""
import threading
import logging
from typing import Callable, Dict, List, Any
from collections import defaultdict

logger = logging.getLogger("EventBus")


class EventBus:
    """线程安全发布订阅总线 — 单例模式"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._subscribers: Dict[str, List[Callable]] = defaultdict(list)
                    obj._sub_lock = threading.Lock()
                    cls._instance = obj
        return cls._instance

    def subscribe(self, event_type: str, callback: Callable):
        """订阅事件 — 可重复调用"""
        with self._sub_lock:
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable):
        """取消订阅"""
        with self._sub_lock:
            self._subscribers[event_type] = [
                cb for cb in self._subscribers[event_type] if cb != callback
            ]

    def publish(self, event_type: str, data: Any = None):
        """发布事件 — 在调用线程同步执行所有订阅者"""
        with self._sub_lock:
            callbacks = list(self._subscribers[event_type])
        for cb in callbacks:
            try:
                cb(data)
            except Exception as e:
                logger.error(f"订阅者异常 [{event_type}]: {e}", exc_info=False)

    def publish_async(self, event_type: str, data: Any = None):
        """异步发布 — 在后台守护线程执行，不阻塞主线程"""
        t = threading.Thread(
            target=self.publish, args=(event_type, data),
            daemon=True, name=f"eb-{event_type}"
        )
        t.start()

    def subscriber_count(self, event_type: str) -> int:
        """获取某事件类型的订阅者数量"""
        with self._sub_lock:
            return len(self._subscribers.get(event_type, []))

    def clear(self):
        """清除所有订阅（仅用于测试）"""
        with self._sub_lock:
            self._subscribers.clear()


# ── 事件类型常量 ──────────────────────────────────────
class Events:
    """事件类型枚举"""
    MATERIAL_UPDATED   = "material.updated"      # 素材库更新
    MATERIAL_ANALYZED  = "material.analyzed"     # 素材分析完成
    GENERATION_STARTED = "generation.started"    # 视频生成开始
    GENERATION_DONE    = "generation.done"       # 视频生成完成
    GENERATION_FAILED  = "generation.failed"     # 视频生成失败
    LEARNING_DONE      = "learning.done"         # 自学习完成
    REVIEW_PENDING     = "review.pending"        # 有待审核规则
    QUALITY_RESULT     = "quality.result"        # 质检结果
    LOG_MESSAGE        = "log.message"           # 日志消息
    PROGRESS_UPDATE    = "progress.update"        # 进度更新
    RETRY_SCHEDULED    = "retry.scheduled"        # 重试已调度
    CONFIG_CHANGED     = "config.changed"         # 配置变更
    DB_READY           = "db.ready"              # 数据库就绪
    SCAN_COMPLETE      = "scan.complete"         # 扫描完成
    MODEL_LOADED       = "model.loaded"          # 模型加载完成


# ── 全局单例访问 ──────────────────────────────────────
_bus: EventBus = None

def get_bus() -> EventBus:
    """获取全局事件总线单例"""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def publish(event_type: str, data: Any = None):
    """便捷发布函数"""
    get_bus().publish(event_type, data)


def subscribe(event_type: str, callback: Callable):
    """便捷订阅函数"""
    get_bus().subscribe(event_type, callback)


def publish_async(event_type: str, data: Any = None):
    """便捷异步发布函数"""
    get_bus().publish_async(event_type, data)
