"""
树剪 TreeCut v12.2 — 基础权限中间件
====================================
API密钥校验 + 访问频率限制 + 角色权限控制。
供 Web UI (ui/web.py) 和未来的 HTTP API 使用。
"""
import time
import threading
from datetime import datetime
import logging
from typing import Tuple, Dict

_log = logging.getLogger("TreeCut.AuthMiddleware")


class AuthMiddleware:
    """API密钥校验 + 频率限制"""

    def __init__(self, max_requests_per_minute: int = 60):
        self._valid_keys: Dict[str, Dict] = {}  # api_key → {user_id, role}
        self._rate_limit: Dict[str, list] = {}   # user_id → [timestamps]
        self._lock = threading.Lock()
        self._max_rpm = max_requests_per_minute
        _log.info(f"权限中间件就绪 (限流={max_requests_per_minute}rpm)")

    def add_key(self, api_key: str, user_id: str, role: str = "user"):
        """注册有效API密钥"""
        with self._lock:
            self._valid_keys[api_key] = {"user_id": user_id, "role": role, "created": time.time()}
        _log.info(f"已注册密钥: user={user_id}, role={role}")

    def revoke_key(self, api_key: str):
        """吊销密钥"""
        with self._lock:
            self._valid_keys.pop(api_key, None)

    def verify(self, api_key: str) -> Tuple[bool, str, Dict]:
        """
        校验密钥 + 频率限制。
        返回: (是否通过, 消息, 用户信息)
        """
        if api_key not in self._valid_keys:
            _log.warning(f"无效API密钥: {api_key[:8]}...")
            return False, "无效的API密钥", {}

        user_info = self._valid_keys[api_key]
        user_id = user_info["user_id"]

        # 频率限制
        with self._lock:
            now = time.time()
            if user_id not in self._rate_limit:
                self._rate_limit[user_id] = []
            # 清除过期记录
            self._rate_limit[user_id] = [ts for ts in self._rate_limit[user_id] if now - ts < 60]

            if len(self._rate_limit[user_id]) >= self._max_rpm:
                _log.warning(f"用户 {user_id} 触发频率限制")
                return False, f"请求过于频繁(>{self._max_rpm}次/分钟)", user_info

            self._rate_limit[user_id].append(now)

        return True, "OK", user_info

    def check_role(self, user_info: Dict, required_role: str) -> bool:
        """检查用户是否拥有指定角色权限"""
        hierarchy = {"admin": 3, "editor": 2, "user": 1}
        user_level = hierarchy.get(user_info.get("role", "user"), 1)
        required_level = hierarchy.get(required_role, 1)
        return user_level >= required_level

    def get_key_count(self) -> int:
        """获取已注册密钥数"""
        with self._lock:
            return len(self._valid_keys)

    # ═════════ ★ v12.3: 用户配额管理 ═════════
    def get_quota(self, user_id: str) -> dict:
        """查询用户配额详情"""
        import time as _t
        today = _t.strftime("%Y%m%d")

        # 查找角色
        role = "user"
        daily_total = 50
        for info in self._valid_keys.values():
            if info["user_id"] == user_id:
                role = info["role"]
                break

        quota_map = {"admin": 9999, "editor": 200, "user": 50}
        daily_total = quota_map.get(role, 50)

        with self._lock:
            if user_id not in self._rate_limit:
                used = 0
            else:
                now_ts = _t.time()
                used = sum(1 for ts in self._rate_limit.get(user_id, []) if now_ts - ts < 86400)

        return {
            "user_id": user_id,
            "role": role,
            "daily_total": daily_total,
            "today_used": min(used, daily_total),
            "today_remaining": max(daily_total - used, 0),
        }

    def check_quota(self, user_id: str, role: str = None) -> tuple:
        """检查并扣除配额 (原子操作)"""
        import time as _t
        today = _t.strftime("%Y%m%d")

        # 用 verify 中的频率限制做基础配额
        quota_map = {"admin": 9999, "editor": 200, "user": 50}
        effective_role = role or "user"
        max_rpm = quota_map.get(effective_role, 50)

        with self._lock:
            if user_id not in self._rate_limit:
                self._rate_limit[user_id] = []
            now = _t.time()
            # 24小时窗口
            self._rate_limit[user_id] = [ts for ts in self._rate_limit[user_id] if now - ts < 86400]
            used = len(self._rate_limit[user_id])

            if used >= max_rpm:
                return False, f"日配额已用完({used}/{max_rpm})", used

            self._rate_limit[user_id].append(now)
            return True, "OK", used + 1

    def get_operation_logs(self, limit: int = 50) -> list:
        """获取操作审计日志"""
        return self._operation_logs[-limit:] if hasattr(self, '_operation_logs') else []

    def log_operation(self, user_id: str, op: str, ok: bool, msg: str = ""):
        """记录操作(供外部调用)"""
        if not hasattr(self, '_operation_logs'):
            self._operation_logs = []
        self._operation_logs.append({
            "user_id": user_id, "operation": op, "success": ok,
            "message": msg, "time": datetime.now().isoformat(),
        })
        if len(self._operation_logs) > 10000:
            self._operation_logs = self._operation_logs[-10000:]


_auth: AuthMiddleware = None

def get_auth() -> AuthMiddleware:
    global _auth
    if _auth is None:
        _auth = AuthMiddleware()
    return _auth
