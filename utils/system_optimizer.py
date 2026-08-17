"""
系统硬件优化模块
CPU亲和性绑定、进程优先级提升、内存管理
"""
import os
import sys
import psutil
from utils.logging import get_loguru_logger as get_logger
logger = get_logger("system_optimizer")
def set_process_priority(priority: str = "high"):
    """设置进程优先级（Windows: HIGH_PRIORITY_CLASS）"""
    if sys.platform != "win32":
        return
    try:
        p = psutil.Process(os.getpid())
        priority_map = {
            "low": psutil.IDLE_PRIORITY_CLASS,
            "normal": psutil.NORMAL_PRIORITY_CLASS,
            "high": psutil.HIGH_PRIORITY_CLASS,
        }
        p.nice(priority_map.get(priority, psutil.NORMAL_PRIORITY_CLASS))
        logger.info(f"进程优先级设置为: {priority}")
    except Exception as e:
        logger.warning(f"设置优先级失败: {e}")
def set_cpu_affinity(core_count: int = 10):
    """绑定CPU核心到前N个逻辑处理器"""
    if sys.platform != "win32":
        return
    try:
        p = psutil.Process(os.getpid())
        p.cpu_affinity(list(range(core_count)))
        logger.info(f"CPU核心绑定完成，使用{core_count}个逻辑核心")
    except Exception as e:
        logger.warning(f"设置CPU亲和性失败: {e}")
def optimize_for_hardware(config: dict):
    """执行全量系统级硬件优化"""
    perf_cfg = config.get("performance", {})
    if perf_cfg.get("process_priority"):
        set_process_priority(perf_cfg["process_priority"])
    if perf_cfg.get("enable_cpu_affinity"):
        set_cpu_affinity(perf_cfg.get("cpu_threads", 10))
    logger.info("系统级硬件优化执行完成")

# ── v12.2: 兼容树剪.py启动时调用的入口函数 ──

def auto_optimize() -> dict:
    """自动检测硬件并执行优化，返回系统报告 (树剪.py 启动入口)"""
    import os
    cpu_cores = os.cpu_count() or 8
    effective_cores = max(1, cpu_cores - 2)  # 保留2核给系统

    # CPU亲和性
    try:
        set_cpu_affinity(effective_cores)
        set_process_priority("high")
    except Exception:
        pass

    # GPU检测
    gpu_available = False
    gpu_vram_mb = 0
    try:
        from utils.vram_manager import get_nvidia_vram_info
        vram = get_nvidia_vram_info()
        gpu_vram_mb = vram.get("total_mb", 0)
        gpu_available = gpu_vram_mb > 0
    except Exception:
        pass

    # 内存检测
    total_memory_mb = 8192  # 默认8GB
    try:
        import psutil
        total_memory_mb = psutil.virtual_memory().total // (1024 * 1024)
    except Exception:
        pass

    # 缓存大小: 总内存的25%，最小256MB，最大2048MB
    memory_cache_mb = max(256, min(2048, total_memory_mb // 4))

    logger.info(f"硬件优化完成: CPU={effective_cores}/{cpu_cores} "
                f"GPU={'%.1fGB'%(gpu_vram_mb/1024) if gpu_available else 'N/A'} "
                f"RAM={total_memory_mb//1024}GB MemCache={memory_cache_mb}MB")

    return {
        "cpu_cores": cpu_cores,
        "effective_cores": effective_cores,
        "gpu_available": gpu_available,
        "gpu_vram_mb": gpu_vram_mb,
        "total_memory_mb": total_memory_mb,
        "memory_cache_mb": memory_cache_mb,
    }
