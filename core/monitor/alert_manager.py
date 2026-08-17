"""
告警管理器 — 多渠道告警推送 + 冷却控制。
"""
import time
import threading
import logging
from typing import Dict
from datetime import datetime

_log = logging.getLogger("TreeCut.Monitor")


class AlertManager:
    """异常告警管理器"""

    def __init__(self, cooldown_sec: int = 300):
        self._cooldown = cooldown_sec
        self._last_alert: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._webhook_url = ""

    def set_webhook(self, url: str):
        self._webhook_url = url

    def send(self, alert_type: str, message: str, level: str = "warning") -> bool:
        """发送告警（含冷却控制）"""
        with self._lock:
            now = time.time()
            last = self._last_alert.get(alert_type, 0)
            if now - last < self._cooldown:
                return False
            self._last_alert[alert_type] = now

        timestamp = datetime.now().strftime("%m-%d %H:%M:%S")
        full_msg = f"[{timestamp}][{level.upper()}] {alert_type}: {message}"
        _log.warning(full_msg)

        # EventBus推送
        try:
            from core.event_bus import get_bus, Events
            get_bus().publish_async(Events.LOG_MESSAGE, {
                "level": level, "module": "AlertManager", "message": full_msg
            })
        except Exception:
            pass

        return True

    def alert_task_fail(self, task_id: str, error: str):
        self.send("task_failed", f"任务 {task_id} 失败: {error}", "error")

    def alert_high_load(self, qps: float, queue_size: int):
        self.send("high_load", f"QPS={qps} queue={queue_size}", "warning")

    def alert_review_pending(self, count: int):
        self.send("review_pending", f"待审核项: {count}", "info")


_alert: AlertManager = None

def get_alert_manager() -> AlertManager:
    global _alert
    if _alert is None:
        _alert = AlertManager()
    return _alert
