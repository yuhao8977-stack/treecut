"""
树剪 TreeCut v12.2 — 通用工具库
===============================
从架构升级中提取的通用基础工具: 耗时装饰器、文本哈希、分句等。
所有模块可直接引用。
"""
import re
import hashlib
import time as _time
from functools import wraps
from typing import Callable, Any, List


def time_cost(func: Callable) -> Callable:
    """
    耗时统计装饰器 — 自动记录函数执行时间。
    用法: @time_cost / def my_func(): ...
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = _time.time()
        result = func(*args, **kwargs)
        cost = round(_time.time() - start, 3)
        try:
            from utils.logging import get_logger
            get_logger("Perf").debug(f"{func.__name__} 耗时 {cost}s")
        except Exception:
            pass
        return result
    return wrapper


def md5_hash(text: str) -> str:
    """生成文本MD5哈希 — 用于素材去重、脚本指纹"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def sha256_hash(text: str) -> str:
    """生成文本SHA256哈希 — 用于安全校验"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_text_by_sentence(text: str) -> List[str]:
    """
    按中英文标点拆分文案为句子列表。
    支持: 。！？.!? ；; 换行
    """
    if not text or not text.strip():
        return []
    # 用正则按标点拆分
    parts = re.split(r'[。！？.!?；;\n]+', text.strip())
    return [s.strip() for s in parts if s.strip()]


def truncate_text(text: str, max_len: int = 200) -> str:
    """截断文本，超出部分用...替代"""
    if len(text) <= max_len:
        return text
    return text[:max_len-3] + "..."


def safe_json_loads(text: str, default: Any = None) -> Any:
    """安全JSON解析，失败返回默认值"""
    import json
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default


def format_duration(seconds: float) -> str:
    """秒数转为可读格式 MM:SS"""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def format_srt_time(seconds: float) -> str:
    """秒数转为SRT时间格式 HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
