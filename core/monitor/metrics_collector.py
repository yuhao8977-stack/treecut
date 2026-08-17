"""
指标采集器 — QPS/耗时/成功率统计。
"""
import time
import threading
from collections import defaultdict
from typing import Dict, List
import logging

_log = logging.getLogger("TreeCut.Monitor")


class MetricsCollector:
    """系统指标采集器"""

    def __init__(self):
        self._counters = defaultdict(int)
        self._latencies: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()
        self._start = time.time()

    def record(self, api: str, cost: float, success: bool = True):
        with self._lock:
            suffix = "success" if success else "fail"
            self._counters[f"{api}_{suffix}"] += 1
            self._counters[f"{api}_total"] += 1
            if success:
                self._latencies[api].append(cost)

    def get_summary(self) -> Dict:
        with self._lock:
            uptime = time.time() - self._start
            apis = {}
            for key in set(k.rsplit("_", 1)[0] for k in self._counters):
                total = self._counters.get(f"{key}_total", 0)
                success = self._counters.get(f"{key}_success", 0)
                lats = self._latencies.get(key, [])
                apis[key] = {
                    "total": total,
                    "success": success,
                    "success_rate": f"{(success/max(total,1)*100):.1f}%",
                    "avg_latency_ms": round(sum(lats)/len(lats)*1000, 1) if lats else 0,
                    "qps": round(total/max(uptime,1), 1),
                }
            return {"uptime_sec": round(uptime), "apis": apis}

    def reset(self):
        with self._lock:
            self._counters.clear()
            self._latencies.clear()
            self._start = time.time()
        _log.info("指标已重置")


_metrics: MetricsCollector = None

def get_metrics() -> MetricsCollector:
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics
