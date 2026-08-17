"""
全局模型池 - 懒加载 + LRU淘汰 + 显存智能管控
冷启动≤3秒，闲置模型自动卸载释放显存
"""
import time
import threading
from collections import OrderedDict
from utils.logging import get_loguru_logger as get_logger
from utils.vram_manager import get_nvidia_vram_info
from core.config_loader import CONFIG
logger = get_logger("model_pool")
class ModelPool:
    """全局模型池单例：按需加载，LRU淘汰，显存峰值管控"""
    _instance = None
    _lock = threading.Lock()
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.models = OrderedDict()
        self.last_used_time = {}
        self.max_vram = CONFIG["model_pool"]["max_vram_mb"]
        self.idle_timeout = CONFIG["model_pool"]["lru_idle_minutes"] * 60
        self.resident_models = set(CONFIG["model_pool"]["resident_models"])
        self._lock = threading.Lock()
        # 后台闲置清理线程
        self._start_cleaner()
        logger.info(f"全局模型池初始化完成 | 显存上限: {self.max_vram}MB | 常驻: {self.resident_models}")
    def _start_cleaner(self):
        """后台线程：每60秒清理闲置超时模型"""
        def cleaner():
            while True:
                time.sleep(60)
                self._clean_idle_models()
        t = threading.Thread(target=cleaner, daemon=True)
        t.start()
    def _clean_idle_models(self):
        """清理超过空闲时间的非常驻模型"""
        now = time.time()
        with self._lock:
            to_remove = []
            for name in list(self.models.keys()):
                if name in self.resident_models:
                    continue
                idle_time = now - self.last_used_time.get(name, 0)
                if idle_time > self.idle_timeout:
                    to_remove.append(name)
            for name in to_remove:
                del self.models[name]
                self.last_used_time.pop(name, None)
                logger.info(f"闲置模型已卸载: {name}（空闲{self.idle_timeout//60}分钟）")
    def get_model(self, model_name: str, loader_func):
        """
        获取模型，不存在则调用loader_func懒加载
        返回: 模型实例
        """
        with self._lock:
            # 命中缓存
            if model_name in self.models:
                self.last_used_time[model_name] = time.time()
                self.models.move_to_end(model_name)
                return self.models[model_name]
            # 显存检查 → 不足时驱逐非常驻模型
            vram_info = get_nvidia_vram_info()
            if vram_info["total_mb"] > 0 and vram_info["free_mb"] < 500:
                self._evict_models(required_mb=800)
            # 懒加载
            logger.info(f"加载模型: {model_name}")
            try:
                model = loader_func()
            except Exception as e:
                logger.error(f"模型加载失败 {model_name}: {e}")
                raise
            self.models[model_name] = model
            self.last_used_time[model_name] = time.time()
            return model
    def _evict_models(self, required_mb: int):
        """按LRU顺序驱逐非常驻模型，释放显存"""
        evicted = 0
        for name in list(self.models.keys()):
            if name in self.resident_models:
                continue
            del self.models[name]
            self.last_used_time.pop(name, None)
            evicted += 500
            logger.info(f"显存不足，驱逐模型: {name}")
            if evicted >= required_mb:
                break
    def release_all(self):
        """释放所有已加载模型"""
        with self._lock:
            count = len(self.models)
            self.models.clear()
            self.last_used_time.clear()
            logger.info(f"所有模型已释放，共{count}个")
    @property
    def loaded_models(self) -> list:
        """当前已加载的模型名称列表"""
        with self._lock:
            return list(self.models.keys())
# 全局单例
model_pool = ModelPool()
