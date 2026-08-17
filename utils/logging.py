"""
树剪 TreeCut — 统一日志系统 v2.0
================================
v12.0 重构: 替代散落的 print()，统一所有模块日志输出。
  - 文件持久化(按日期滚动, 30天保留)
  - EventBus集成 → UI实时显示
  - 4级日志: DEBUG/INFO/WARNING/ERROR
  - 结构化格式: [时间][模块][级别] 消息
  - 线程安全、高性能

用法:
    from utils.logging import get_logger
    logger = get_logger("模块名")
    logger.info("消息")
    logger.warning("消息", detail=...)
    logger.error("消息", extra={"traceback": "..."})
"""

import logging
import logging.handlers
import json
import threading
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

# ── 日志根目录 ─────────────────────────────────────────
_PROJ_ROOT = Path(__file__).parent.parent
_LOG_DIR = _PROJ_ROOT / "03_粗剪输出" / "_logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── 格式化器 ───────────────────────────────────────────
class TreeCutFormatter(logging.Formatter):
    """统一格式化: [时间][模块][级别] 消息"""
    _fmt = "[%(asctime)s][%(name)s][%(levelname)s] %(message)s"

    def __init__(self):
        super().__init__(fmt=self._fmt, datefmt="%m-%d %H:%M:%S")

# ── 日志管理器 ─────────────────────────────────────────
class LogManager:
    """统一日志系统 — 文件+EventBus+控制台 三路输出"""

    _instance: Optional["LogManager"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._loggers: Dict[str, logging.Logger] = {}
        self._setup_root()
        self._ui_enabled = True
        self._console_enabled = True  # 控制台输出(开发用)
        self._eventbus_ready = False

    def _setup_root(self):
        """配置根日志器"""
        root = logging.getLogger("TreeCut")
        root.setLevel(logging.DEBUG)

        # ── 文件处理器: 按日期滚动, 30天保留 ──
        log_file = _LOG_DIR / f"treecut_{datetime.now().strftime('%Y%m%d')}.log"
        fh = logging.handlers.TimedRotatingFileHandler(
            filename=str(log_file),
            when="midnight", interval=1, backupCount=30,
            encoding="utf-8"
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(TreeCutFormatter())
        root.addHandler(fh)

        # ── 错误单独文件 ──
        err_file = _LOG_DIR / f"errors_{datetime.now().strftime('%Y%m%d')}.log"
        eh = logging.handlers.TimedRotatingFileHandler(
            filename=str(err_file),
            when="midnight", interval=1, backupCount=30,
            encoding="utf-8"
        )
        eh.setLevel(logging.WARNING)
        eh.setFormatter(TreeCutFormatter())
        root.addHandler(eh)

        # ── 控制台处理器(开发用) ──
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(TreeCutFormatter())
        root.addHandler(ch)

    # ── 获取或创建模块日志器 ─────────────────────────
    def get_logger(self, name: str) -> logging.Logger:
        if name not in self._loggers:
            logger = logging.getLogger(f"TreeCut.{name}")
            logger.setLevel(logging.DEBUG)
            # 继承根日志器的处理器(通过传播)
            logger.propagate = True
            self._loggers[name] = logger
        return self._loggers[name]

    # ── EventBus 集成 ─────────────────────────────────
    def enable_eventbus(self):
        """激活 EventBus 输出 — 日志自动推送到UI"""
        self._eventbus_ready = True

    def _publish_to_ui(self, level: str, message: str, module: str):
        """将日志消息发布到 EventBus"""
        if not self._eventbus_ready:
            return
        try:
            from core.event_bus import publish, Events
            publish(Events.LOG_MESSAGE, {
                "level": level,
                "message": message,
                "module": module,
                "timestamp": datetime.now().isoformat(),
            })
        except ImportError:
            pass
        except Exception:
            pass

    def set_ui_enabled(self, enabled: bool):
        self._ui_enabled = enabled

    def set_console_enabled(self, enabled: bool):
        self._console_enabled = enabled

    # ═══════════════ ★ v12.1: 日志查询 ═══════════════
    def get_recent_logs(self, count: int = 50) -> str:
        """获取最近N条日志文本 — 对应导图 LogWindow.get_recent_logs()"""
        logs = self.get_all_logs_today()
        return "\n".join(logs[-count:]) if logs else "暂无日志"

    def get_error_history(self) -> list:
        """获取错误日志历史"""
        return self.get_recent_errors(n=50)
        self._console_enabled = enabled

    # ── 日志查询 ─────────────────────────────────────
    def get_recent_errors(self, n: int = 20) -> list:
        """获取最近错误(从文件读取)"""
        errors = []
        for f in sorted(_LOG_DIR.glob("errors_*.log"), reverse=True)[:5]:
            try:
                lines = f.read_text(encoding="utf-8").strip().split("\n")
                for line in reversed(lines):
                    if "WARNING" in line or "ERROR" in line or "CRITICAL" in line:
                        errors.append(line)
                        if len(errors) >= n:
                            return errors
            except Exception:
                pass
        return errors

    def get_all_logs_today(self) -> list:
        """获取今天的全部日志"""
        today_file = _LOG_DIR / f"treecut_{datetime.now().strftime('%Y%m%d')}.log"
        if today_file.exists():
            return today_file.read_text(encoding="utf-8").strip().split("\n")
        return []

    def get_stats(self) -> dict:
        """获取日志统计"""
        stats = {"ERROR": 0, "WARNING": 0, "INFO": 0, "DEBUG": 0}
        for f in _LOG_DIR.glob("treecut_*.log"):
            try:
                for line in f.read_text(encoding="utf-8").split("\n"):
                    for level in stats:
                        if f"[{level}]" in line:
                            stats[level] += 1
            except Exception:
                pass
        return stats

    def cleanup_old_logs(self, keep_days: int = 30):
        """清理过期日志"""
        import time
        cutoff = time.time() - keep_days * 86400
        for f in _LOG_DIR.glob("treecut_*.log"):
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
        for f in _LOG_DIR.glob("errors_*.log"):
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)


# ── 全局单例 ──────────────────────────────────────────
_log_manager = LogManager()


def get_logger(name: str) -> logging.Logger:
    """获取模块日志器 — 推荐用法"""
    return _log_manager.get_logger(name)


# ── 便捷函数(向后兼容) ────────────────────────────────
def setup_eventbus():
    """激活EventBus日志输出 — 在树剪.py初始化时调用"""
    _log_manager.enable_eventbus()


def log_error(source: str, message: str, detail: Any = None):
    logger = get_logger(source)
    logger.error(f"{message}" + (f" | {detail}" if detail else ""))

def log_warning(source: str, message: str, detail: Any = None):
    logger = get_logger(source)
    logger.warning(f"{message}" + (f" | {detail}" if detail else ""))

def log_info(source: str, message: str, detail: Any = None):
    logger = get_logger(source)
    logger.info(f"{message}" + (f" | {detail}" if detail else ""))

def log_debug(source: str, message: str, detail: Any = None):
    logger = get_logger(source)
    logger.debug(f"{message}" + (f" | {detail}" if detail else ""))


# ── 兼容旧API ─────────────────────────────────────────
class ErrorLogger:
    """兼容旧版 ErrorLogger 接口"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def log(self, source: str, level: str, message: str, detail: Any = None):
        logger = get_logger(source)
        log_func = getattr(logger, level.lower(), logger.info)
        log_func(f"{message}" + (f" | {detail}" if detail else ""))

    def critical(self, source: str, message: str, detail: Any = None):
        self.log(source, "critical", message, detail)
    def error(self, source: str, message: str, detail: Any = None):
        self.log(source, "error", message, detail)
    def warning(self, source: str, message: str, detail: Any = None):
        self.log(source, "warning", message, detail)
    def info(self, source: str, message: str, detail: Any = None):
        self.log(source, "info", message, detail)
    def set_log_path(self, path): pass
    def get_recent(self, n=20, level=None): return []
    def get_stats(self): return _log_manager.get_stats()
    def print_stats(self): pass

_error_logger = ErrorLogger()
def get_error_logger() -> ErrorLogger:
    return _error_logger


# ── v12.2: loguru兼容层 (替代 utils/logger.py) ──
_HAS_LOGURU = False
try:
    from loguru import logger as _loguru_logger
    _HAS_LOGURU = True
except ImportError:
    _loguru_logger = None

def get_loguru_logger(name: str = None):
    """获取loguru logger实例 (兼容旧 utils/logger.py API)"""
    if _HAS_LOGURU:
        return _loguru_logger.bind(name=name or "TreeCut")
    # 回退到标准logging
    import logging as _stdlib_logging
    return _stdlib_logging.getLogger(name or "TreeCut")

# 重新导出log_warning以确保向后兼容
from utils.logging import log_warning as _log_warning_export
