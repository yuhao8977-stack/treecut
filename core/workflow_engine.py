"""
工作流引擎 v3.0 - 断点续跑 + 插件编排 + 全链路闭环
质检 → 纠错 → 复检 → 归档，支持崩溃恢复
"""
import pickle
import time
from utils.logging import get_loguru_logger as get_logger
from utils.vram_manager import release_gpu_memory
from core.database import execute_sql, query_sql
from core.config_loader import CONFIG
from core.plugin_manager import plugin_manager
logger = get_logger("workflow")
# 节点执行顺序
WORKFLOW_NODES = [
    ("start", None),
    ("video_split", ("recognize", "video_split")),
    ("audio_transcribe", ("recognize", "audio_transcribe")),
    ("subtitle_ocr", ("recognize", "subtitle_ocr")),
    ("scene_tag", ("recognize", "scene_tag")),
    ("bgm_classify", ("recognize", "bgm_classify")),
    ("quality_black", ("quality", "black_frame")),
    ("quality_param", ("quality", "param_check")),
    ("quality_blur", ("quality", "blur_stutter")),
    ("quality_aspect", ("quality", "aspect_check")),
    ("quality_sync", ("quality", "subtitle_sync")),
    ("quality_brand", ("quality", "brand_detect")),
    ("quality_summary", None),
    ("auto_correct", ("correct", "trim_black")),
    ("recheck", None),
    ("archive", None),
    ("end", None),
]
class WorkflowEngine:
    """工作流引擎：断点续跑 + 插件执行 + 自动降级"""
    def __init__(self):
        self.enable_persistence = CONFIG["workflow"]["enable_persistence"]
        self.retry_times = CONFIG["workflow"]["auto_retry_times"]
        logger.info("工作流引擎 v3.0 初始化完成，支持断点续跑")
    def _execute_node(self, node_name: str, plugin_ref: tuple | None, material_id: int, video_path: str) -> bool:
        """执行单个工作流节点"""
        logger.debug(f"执行节点: {node_name}")
        execute_sql(
            "UPDATE tasks SET current_node=? WHERE material_id=?",
            (node_name, material_id)
        )
        # 特殊节点
        if node_name == "quality_summary":
            issues = query_sql(
                "SELECT COUNT(*) FROM quality_results WHERE material_id=? AND is_fixed=0",
                (material_id,)
            )
            count = issues[0][0] if issues else 0
            logger.info(f"质检汇总，待处理问题: {count}个")
            return True
        if node_name == "recheck":
            logger.info("执行自动复检")
            return self._recheck(material_id, video_path)
        if node_name in ("start", "archive", "end"):
            return True
        # 插件节点
        if plugin_ref:
            category, plugin_name = plugin_ref
            plugin = plugin_manager.get_plugin(category, plugin_name)
            if plugin is None:
                logger.warning(f"插件未注册，跳过: {category}/{plugin_name}")
                return True
            for attempt in range(self.retry_times):
                try:
                    result = plugin.run(material_id, video_path)
                    if result.get("status") in ("success", "cached", "skipped"):
                        return True
                    # 非关键节点（识别类+品牌检测）失败不中断流程
                    skippable = {"audio_transcribe", "subtitle_ocr", "scene_tag", "bgm_classify", "quality_brand"}
                    if node_name in skippable:
                        logger.warning(f"非关键节点{node_name}跳过: {result.get('status')}")
                        return True
                    logger.warning(f"关键节点{node_name}返回非成功: {result.get('status')}")
                    return False
                except RuntimeError as e:
                    if "out of memory" in str(e).lower() and CONFIG["workflow"]["auto_degrade_on_oom"]:
                        logger.warning(f"节点{node_name}显存溢出，第{attempt+1}次重试")
                        release_gpu_memory()
                        continue
                    raise
                except Exception as e:
                    if attempt < self.retry_times - 1:
                        logger.warning(f"节点{node_name}异常，第{attempt+1}次重试: {e}")
                        continue
                    raise
        return True
    def _recheck(self, material_id: int, video_path: str) -> bool:
        """复检：重新执行核心质检项"""
        recheck_plugins = [
            ("quality", "black_frame"),
            ("quality", "param_check"),
            ("quality", "blur_stutter"),
            ("quality", "aspect_check"),
            ("quality", "subtitle_sync"),
        ]
        for category, name in recheck_plugins:
            plugin = plugin_manager.get_plugin(category, name)
            if plugin:
                try:
                    plugin.run(material_id, video_path)
                except Exception as e:
                    logger.warning(f"复检{category}/{name}失败: {e}")
        logger.info("自动复检完成")
        return True
    def run(self, material_id: int, video_path: str, task_id: int = None) -> dict:
        """
        运行全链路工作流
        task_id: 可选，支持从指定任务断点续跑
        """
        logger.info(f"启动工作流，素材ID: {material_id}")
        execute_sql(
            "INSERT OR IGNORE INTO tasks (material_id, task_type, status, current_node) VALUES (?, 'full_process', 'running', 'start')",
            (material_id,)
        )
        execute_sql(
            "UPDATE tasks SET status='running', progress=0 WHERE material_id=?", (material_id,)
        )
        # 断点续跑：检查是否有已保存的状态
        start_index = 0
        if task_id and self.enable_persistence:
            saved = query_sql("SELECT workflow_state FROM tasks WHERE id=?", (task_id,))
            if saved and saved[0][0]:
                try:
                    state = pickle.loads(saved[0][0])
                    saved_node = state.get("current_node", "start")
                    for i, (node_name, _) in enumerate(WORKFLOW_NODES):
                        if node_name == saved_node:
                            start_index = i + 1
                            break
                    logger.info(f"从断点恢复，从节点 {saved_node} 之后继续")
                except Exception as e:
                    logger.warning(f"断点状态解析失败: {e}，从头执行")
        current_path = video_path
        total = len(WORKFLOW_NODES)
        try:
            for i in range(start_index, total):
                node_name, plugin_ref = WORKFLOW_NODES[i]
                progress = int((i + 1) / total * 100)
                execute_sql(
                    "UPDATE tasks SET progress=? WHERE material_id=?", (progress, material_id)
                )
                success = self._execute_node(node_name, plugin_ref, material_id, current_path)
                if not success:
                    raise Exception(f"节点执行失败: {node_name}")
                # 持久化断点状态
                if self.enable_persistence:
                    state = pickle.dumps({"current_node": node_name, "progress": progress})
                    execute_sql(
                        "UPDATE tasks SET workflow_state=? WHERE material_id=?",
                        (state, material_id)
                    )
                # 纠错节点后更新路径
                if node_name == "auto_correct":
                    updated = query_sql(
                        "SELECT file_path FROM materials WHERE id=?", (material_id,)
                    )
                    if updated:
                        current_path = updated[0][0]
                release_gpu_memory()
            # 完成
            execute_sql(
                "UPDATE tasks SET status='completed', progress=100 WHERE material_id=?",
                (material_id,)
            )
            execute_sql(
                "UPDATE materials SET status='processed' WHERE id=?", (material_id,)
            )
            final_issues = query_sql(
                "SELECT COUNT(*) FROM quality_results WHERE material_id=? AND is_fixed=0",
                (material_id,)
            )
            remaining = final_issues[0][0] if final_issues else 0
            logger.info(f"工作流执行完成 | 素材ID: {material_id} | 剩余问题: {remaining}个")
            return {"status": "success", "remaining_issues": remaining}
        except Exception as e:
            error_msg = str(e)
            execute_sql(
                "UPDATE tasks SET status='failed', error_msg=? WHERE material_id=?",
                (error_msg, material_id)
            )
            logger.error(f"工作流执行失败: {error_msg}")
            return {"status": "failed", "error": error_msg}
        finally:
            release_gpu_memory()
