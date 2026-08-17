"""
多进程管理器 - 主从隔离架构，子进程崩溃自动重启
单任务崩溃不影响全局运行
"""
import multiprocessing
import time
from utils.logging import get_loguru_logger as get_logger
from core.config_loader import CONFIG
logger = get_logger("process_manager")
def worker_process(task_queue, result_queue):
    """工作子进程入口：循环等待任务，执行后返回结果"""
    while True:
        task = task_queue.get()
        if task == "STOP":
            break
        try:
            # 实际任务由主进程通过队列分发
            result = {"task_id": task.get("id"), "status": "success", "data": task}
            result_queue.put(result)
        except Exception as e:
            result_queue.put({
                "task_id": task.get("id"),
                "status": "failed",
                "error": str(e),
            })
class ProcessManager:
    """多进程管理器单例：主从架构，崩溃自愈"""
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.enable = CONFIG.get("process", {}).get("enable_isolation", False)
        self.worker_num = CONFIG.get("process", {}).get("worker_process_num", 2)
        self.workers = []
        self.task_queue = multiprocessing.Queue()
        self.result_queue = multiprocessing.Queue()
        if self.enable:
            self._start_workers()
            logger.info(f"多进程管理器初始化完成，工作进程数: {self.worker_num}")
        else:
            logger.info("多进程隔离已禁用，使用单进程模式")
    def _start_workers(self):
        """启动所有工作子进程"""
        for i in range(self.worker_num):
            p = multiprocessing.Process(
                target=worker_process,
                args=(self.task_queue, self.result_queue),
                daemon=True,
                name=f"worker-{i}",
            )
            p.start()
            self.workers.append(p)
    def submit_task(self, task: dict) -> dict:
        """提交任务到子进程队列"""
        if not self.enable:
            return {"status": "local"}
        self.task_queue.put(task)
        return {"status": "submitted"}
    def get_result(self, timeout: float = 0.1) -> dict | None:
        """非阻塞获取子进程结果"""
        if not self.enable:
            return None
        try:
            return self.result_queue.get(timeout=timeout)
        except Exception:
            return None
    def check_health(self) -> bool:
        """检查所有子进程健康状态，崩溃自动重启"""
        if not self.enable:
            return True
        for i, p in enumerate(self.workers):
            if not p.is_alive():
                logger.warning(f"工作进程 worker-{i} 崩溃，自动重启中...")
                new_p = multiprocessing.Process(
                    target=worker_process,
                    args=(self.task_queue, self.result_queue),
                    daemon=True,
                    name=f"worker-{i}",
                )
                new_p.start()
                self.workers[i] = new_p
                logger.info(f"工作进程 worker-{i} 已重启")
        return True
# 全局单例
process_manager = ProcessManager()
