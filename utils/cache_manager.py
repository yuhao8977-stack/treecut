"""
两级缓存管理器：内存LRU + SQLite磁盘持久化
"""
import hashlib
import os
import json
from collections import OrderedDict
from utils.logging import get_loguru_logger as get_logger
from core.database import execute_sql, query_sql
logger = get_logger("cache")
class MemoryCache:
    """LRU内存缓存"""
    def __init__(self, max_size_mb: int = 2048):
        self.cache = OrderedDict()
        self.max_size = max_size_mb * 1024 * 1024
        self.current_size = 0
    def get(self, key: str):
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]["data"]
    def set(self, key: str, data):
        try:
            data_size = len(json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"))
        except Exception:
            data_size = 1024 * 1024
        while self.current_size + data_size > self.max_size and self.cache:
            _, oldest_val = self.cache.popitem(last=False)
            self.current_size -= oldest_val.get("size", 0)
        self.cache[key] = {"data": data, "size": data_size}
        self.current_size += data_size
        self.cache.move_to_end(key)
    def invalidate(self, key: str):
        if key in self.cache:
            self.current_size -= self.cache[key].get("size", 0)
            del self.cache[key]
class CacheManager:
    """两级缓存：内存LRU + 数据库持久化"""
    def __init__(self, memory_cache_mb: int = 2048):
        execute_sql('''
            CREATE TABLE IF NOT EXISTS compute_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_hash TEXT NOT NULL,
                cache_type TEXT NOT NULL,
                cache_data TEXT NOT NULL,
                create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(file_hash, cache_type)
            )
        ''')
        self.mem_cache = MemoryCache(max_size_mb=memory_cache_mb)
        logger.info(f"两级缓存初始化完成，内存缓存{memory_cache_mb}MB")
    @staticmethod
    def get_file_hash(file_path: str) -> str:
        if not os.path.exists(file_path):
            return ""
        md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                md5.update(chunk)
        return md5.hexdigest()
    def get(self, file_path: str, cache_type: str):
        """获取缓存"""
        file_hash = self.get_file_hash(file_path)
        if not file_hash:
            return None
        cache_key = f"{cache_type}:{file_hash}"
        # 先查内存
        mem_data = self.mem_cache.get(cache_key)
        if mem_data is not None:
            return mem_data
        # 再查磁盘
        result = query_sql(
            "SELECT cache_data FROM compute_cache WHERE file_hash=? AND cache_type=?",
            (file_hash, cache_type)
        )
        if result:
            data = json.loads(result[0][0])
            self.mem_cache.set(cache_key, data)
            return data
        return None
    def set(self, file_path: str, cache_type: str, data):
        """写入缓存"""
        file_hash = self.get_file_hash(file_path)
        if not file_hash:
            return
        cache_key = f"{cache_type}:{file_hash}"
        self.mem_cache.set(cache_key, data)
        cache_json = json.dumps(data, ensure_ascii=False, default=str)
        exist = query_sql(
            "SELECT id FROM compute_cache WHERE file_hash=? AND cache_type=?",
            (file_hash, cache_type)
        )
        if exist:
            execute_sql(
                "UPDATE compute_cache SET cache_data=?, update_time=CURRENT_TIMESTAMP WHERE file_hash=? AND cache_type=?",
                (cache_json, file_hash, cache_type)
            )
        else:
            execute_sql(
                "INSERT INTO compute_cache (file_hash, cache_type, cache_data) VALUES (?, ?, ?)",
                (file_hash, cache_type, cache_json)
            )
    def invalidate(self, file_path: str, cache_type: str):
        """使缓存失效"""
        file_hash = self.get_file_hash(file_path)
        if file_hash:
            cache_key = f"{cache_type}:{file_hash}"
            self.mem_cache.invalidate(cache_key)
            execute_sql(
                "DELETE FROM compute_cache WHERE file_hash=? AND cache_type=?",
                (file_hash, cache_type)
            )

    def set_memory_cache_size(self, size_mb: int):
        """动态调整内存缓存大小"""
        self.mem_cache.max_size = size_mb * 1024 * 1024
        logger.info(f"内存缓存大小调整为 {size_mb}MB")
# 全局单例
cache_manager = CacheManager()

def get_cache_manager():
    """获取全局缓存管理器单例"""
    return cache_manager
