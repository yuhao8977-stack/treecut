"""
╔══════════════════════════════════════════════════════════════╗
║  🔄 重试与熔断模块                                        ║
║                                                            ║
║  为所有外部 API 调用提供统一的重试和熔断保护：             ║
║  - 指数退避 (Exponential Backoff)                          ║
║  - 熔断器 (Circuit Breaker)                                ║
║  - 超时控制                                                ║
║  - 降级策略                                                ║
║                                                            ║
║  用法:                                                     ║
║    from utils.retry import retry_on_failure        ║
║                                                            ║
║    @retry_on_failure(max_attempts=3, base_delay=1.0)       ║
║    def call_api(url): ...                                  ║
║                                                            ║
║    # 熔断器                                                ║
║    breaker = CircuitBreaker("deepseek", failure_threshold=5)║
║    @breaker.protect                                        ║
║    def risky_call(): ...                                   ║
╚══════════════════════════════════════════════════════════════╝
"""
import time
import random
import functools
import threading
from typing import Callable, Any, Optional, Dict
from datetime import datetime
from collections import defaultdict


# ═══════════════════════════════════════════════════════════════
# 指数退避重试
# ═══════════════════════════════════════════════════════════════

# 可重试的异常类型（网络相关）
RETRYABLE_EXCEPTIONS = (
    ConnectionError, TimeoutError, OSError,
    IOError, BrokenPipeError, ConnectionAbortedError,
    ConnectionResetError, ConnectionRefusedError,
)

# HTTP 可重试状态码
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}


def retry_on_failure(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple = RETRYABLE_EXCEPTIONS,
    on_retry: Optional[Callable] = None,
    on_giveup: Optional[Callable] = None,
):
    """
    指数退避重试装饰器。

    参数:
      max_attempts: 最大尝试次数（含首次）
      base_delay: 首次重试延迟(秒)
      max_delay: 最大延迟上限(秒)
      backoff_factor: 退避倍数
      jitter: 是否添加随机抖动（避免惊群效应）
      retryable_exceptions: 可重试的异常类型
      on_retry: 重试时的回调(exception, attempt, delay)
      on_giveup: 放弃时的回调(exception)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt >= max_attempts - 1:
                        break
                    delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                    if jitter:
                        delay *= 0.5 + random.random()
                    if on_retry:
                        on_retry(e, attempt + 1, delay)
                    time.sleep(delay)
                except Exception as e:
                    # 非可重试异常，直接抛出
                    raise

            if on_giveup:
                on_giveup(last_exception)
            raise last_exception

        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════
# HTTP 请求专用重试（带状态码检查）
# ═══════════════════════════════════════════════════════════════

def http_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 15.0,
):
    """
    HTTP 请求专用重试装饰器。
    自动检查 HTTP 状态码，对 429/5xx 进行重试。
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    result = func(*args, **kwargs)
                    # 如果返回的是 (status_code, data) 格式
                    if isinstance(result, tuple) and len(result) == 2:
                        status, data = result
                        if status in RETRYABLE_HTTP_CODES and attempt < max_attempts - 1:
                            delay = min(base_delay * (2 ** attempt), max_delay)
                            delay *= 0.5 + random.random()
                            time.sleep(delay)
                            continue
                    return result
                except RETRYABLE_EXCEPTIONS as e:
                    last_exception = e
                    if attempt >= max_attempts - 1:
                        raise
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    delay *= 0.5 + random.random()
                    time.sleep(delay)
            raise last_exception
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════
# 熔断器 (Circuit Breaker)
# ═══════════════════════════════════════════════════════════════

class CircuitBreaker:
    """
    熔断器 — 当外部服务连续失败时自动熔断，避免雪崩。

    状态机:
      CLOSED (正常) → OPEN (熔断) → HALF_OPEN (探测) → CLOSED/HALF_OPEN
    """

    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half_open"

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max: int = 3,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max

        self._state = self.STATE_CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._opened_at: Optional[float] = None
        self._lock = threading.Lock()

        # 统计
        self.total_failures = 0
        self.total_successes = 0
        self.total_trips = 0

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == self.STATE_OPEN:
                if time.time() - self._opened_at >= self.recovery_timeout:
                    self._state = self.STATE_HALF_OPEN
                    self._success_count = 0
            return self._state

    def record_success(self):
        with self._lock:
            self.total_successes += 1
            if self._state == self.STATE_HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.half_open_max:
                    self._state = self.STATE_CLOSED
                    self._failure_count = 0
            elif self._state == self.STATE_CLOSED:
                self._failure_count = 0

    def record_failure(self):
        with self._lock:
            self.total_failures += 1
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._state == self.STATE_HALF_OPEN:
                self._state = self.STATE_OPEN
                self._opened_at = time.time()
                self.total_trips += 1
            elif self._failure_count >= self.failure_threshold:
                self._state = self.STATE_OPEN
                self._opened_at = time.time()
                self.total_trips += 1

    def protect(self, func: Callable) -> Callable:
        """保护函数，熔断时直接抛出 CircuitBreakerOpenError"""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if self.state == self.STATE_OPEN:
                remaining = self.recovery_timeout - (time.time() - self._opened_at)
                raise CircuitBreakerOpenError(
                    f"熔断器 [{self.name}] 已断开，{remaining:.0f}秒后恢复"
                )
            try:
                result = func(*args, **kwargs)
                self.record_success()
                return result
            except Exception as e:
                self.record_failure()
                raise e

        return wrapper

    def stats(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self._failure_count,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "total_trips": self.total_trips,
        }


class CircuitBreakerOpenError(Exception):
    """熔断器断开异常"""
    pass


# ═══════════════════════════════════════════════════════════════
# 熔断器注册表（全局管理）
# ═══════════════════════════════════════════════════════════════

class BreakerRegistry:
    """全局熔断器管理器"""

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get(self, name: str, **kwargs) -> CircuitBreaker:
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name=name, **kwargs)
            return self._breakers[name]

    def stats(self) -> Dict[str, dict]:
        return {name: b.stats() for name, b in self._breakers.items()}

    def all_healthy(self) -> bool:
        return all(b.state != CircuitBreaker.STATE_OPEN for b in self._breakers.values())


# 全局实例
breaker_registry = BreakerRegistry()


# ═══════════════════════════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════════════════════════

def call_with_retry(
    func: Callable,
    *args,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    fallback: Any = None,
    **kwargs,
) -> Any:
    """
    同步调用函数，带重试和降级。

    参数:
      func: 要调用的函数
      max_attempts: 最大尝试次数
      base_delay: 基础延迟
      fallback: 全部失败时的降级返回值

    返回: func 的返回值，或 fallback
    """
    decorated = retry_on_failure(max_attempts=max_attempts, base_delay=base_delay)(func)
    try:
        return decorated(*args, **kwargs)
    except Exception:
        return fallback


# ═══════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 50)
    print("  重试与熔断模块自检")
    print("=" * 50)

    # 1. 测试重试
    call_count = [0]

    @retry_on_failure(max_attempts=3, base_delay=0.1)
    def flaky_function():
        call_count[0] += 1
        if call_count[0] < 3:
            raise ConnectionError("网络错误（模拟）")
        return "Success!"

    try:
        result = flaky_function()
        print(f"  重试测试: {result} (共调用{call_count[0]}次)")
    except Exception as e:
        print(f"  重试测试失败: {e}")

    # 2. 测试熔断器
    cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=2.0)

    @cb.protect
    def risky_call(should_fail=True):
        if should_fail:
            raise ConnectionError("服务不可用（模拟）")
        return "OK"

    # 模拟连续失败
    for i in range(3):
        try:
            risky_call(True)
        except ConnectionError:
            pass

    print(f"  3次失败后熔断器状态: {cb.state}")

    # 尝试在熔断状态调用
    try:
        risky_call(False)
    except CircuitBreakerOpenError as e:
        print(f"  熔断保护: {e}")

    print(f"  熔断器统计: {cb.stats()}")
