"""
批量任务队列管理器 - 支持单文件/文件夹导入 + 优先级调度
"""
import os
from utils.logging import get_loguru_logger as get_logger
from core.database import execute_sql, query_sql
from utils.ffmpeg_utils import get_video_info
logger = get_logger("task_queue")
class TaskQueue:
    """批量任务队列（单例）"""
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        logger.info("任务队列管理器初始化完成")
    def add_material(self, file_path: str) -> int:
        """添加单个素材到队列"""
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return -1
        abs_path = os.path.abspath(file_path)
        # 检查是否已存在
        existing = query_sql("SELECT id FROM materials WHERE file_path=?", (abs_path,))
        if existing:
            mid = existing[0][0]
            execute_sql("UPDATE materials SET status='pending' WHERE id=?", (mid,))
        else:
            info = get_video_info(abs_path)
            mid = execute_sql(
                "INSERT INTO materials (file_path, file_type, duration, resolution, fps, bitrate, status) VALUES (?, ?, ?, ?, ?, ?, 'pending')",
                (abs_path, "video", info.get("duration", 0), info.get("resolution", ""), info.get("fps", 0), info.get("bitrate", 0))
            )
        execute_sql(
            "INSERT OR IGNORE INTO task_queue (material_id, status) VALUES (?, 'waiting')",
            (mid,)
        )
        execute_sql(
            "INSERT OR IGNORE INTO tasks (material_id, task_type, status) VALUES (?, 'full_process', 'pending')",
            (mid,)
        )
        logger.info(f"素材已加入队列，ID: {mid}")
        return mid
    def add_folder(self, folder_path: str) -> int:
        """批量导入文件夹中所有视频"""
        if not os.path.isdir(folder_path):
            logger.error(f"目录不存在: {folder_path}")
            return 0
        video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv"}
        count = 0
        for root, _, files in os.walk(folder_path):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in video_exts:
                    self.add_material(os.path.join(root, f))
                    count += 1
        logger.info(f"文件夹批量导入完成，共添加{count}个素材")
        return count
    def run_next(self) -> dict:
        """运行队列中优先级最高的等待任务"""
        from core.workflow_engine import WorkflowEngine
        waiting = query_sql(
            "SELECT id, material_id FROM task_queue WHERE status='waiting' ORDER BY priority DESC, id ASC LIMIT 1"
        )
        if not waiting:
            return {"status": "empty"}
        qid, mid = waiting[0]
        execute_sql("UPDATE task_queue SET status='running' WHERE id=?", (qid,))
        video_path = query_sql("SELECT file_path FROM materials WHERE id=?", (mid,))
        if not video_path:
            return {"status": "failed", "error": "素材不存在"}
        engine = WorkflowEngine()
        result = engine.run(mid, video_path[0][0])
        status = "completed" if result["status"] == "success" else "failed"
        execute_sql("UPDATE task_queue SET status=? WHERE id=?", (status, qid))
        return result
    def run_all(self) -> int:
        """运行所有等待任务"""
        total = 0
        while True:
            result = self.run_next()
            if result.get("status") == "empty":
                break
            total += 1
            if result.get("status") == "failed":
                logger.warning(f"任务{total}失败: {result.get('error', 'unknown')}")
        logger.info(f"批量任务执行完成，共处理{total}个")
        return total
    def list_queue(self) -> list:
        """列出所有队列任务"""
        return query_sql(
            """SELECT q.id, m.file_path, q.status, q.priority, q.create_time
               FROM task_queue q JOIN materials m ON q.material_id = m.id
               ORDER BY q.priority DESC, q.id ASC"""
        )
# 全局单例
task_queue = TaskQueue()
