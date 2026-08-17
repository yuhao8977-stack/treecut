"""
显存检测与管控模块
支持pynvml / nvidia-smi / PyTorch三种检测方式
"""
import os
import sys
import subprocess
from utils.logging import get_loguru_logger as get_logger
logger = get_logger("vram_manager")
def get_nvidia_vram_info() -> dict:
    """获取NVIDIA显卡显存信息（MB单位）"""
    # 方式1: pynvml (Linux/标准环境)
    if sys.platform != "win32":
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            total = info.total // 1024 // 1024
            used = info.used // 1024 // 1024
            free = info.free // 1024 // 1024
            pynvml.nvmlShutdown()
            return {"total_mb": total, "used_mb": used, "free_mb": free}
        except Exception as e:
            logger.debug(f"pynvml获取失败: {e}")
    # 方式2: nvidia-smi命令行
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(", ")
            return {"total_mb": int(parts[0]), "used_mb": int(parts[1]), "free_mb": int(parts[2])}
    except Exception as e:
        logger.debug(f"nvidia-smi失败: {e}")
    # 方式3: PyTorch估算
    try:
        import torch
        if torch.cuda.is_available():
            total = torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)
            reserved = torch.cuda.memory_reserved(0) // (1024 * 1024)
            return {"total_mb": total, "used_mb": reserved, "free_mb": total - reserved}
    except Exception:
        pass
    return {"total_mb": 6144, "used_mb": 0, "free_mb": 6144}
def check_vram_sufficient(required_mb: int) -> bool:
    """检查剩余显存是否充足（120%安全余量）"""
    info = get_nvidia_vram_info()
    if info["total_mb"] == 0:
        return True  # 无GPU时跳过检查
    return info["free_mb"] > required_mb * 1.2
def init_cuda_environment(enable_benchmark: bool = True):
    """初始化CUDA环境变量"""
    os.environ.setdefault("CUDA_DEVICE_ORDER", "PCI_BUS_ID")
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
    if enable_benchmark:
        os.environ.setdefault("CUDNN_BENCHMARK", "1")
    os.environ.setdefault("CUDA_LAUNCH_BLOCKING", "0")
    logger.info("CUDA环境初始化完成")
def release_gpu_memory():
    """释放PyTorch GPU显存缓存"""
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
    except Exception:
        pass

# ── v12.2: 兼容树剪.py启动时调用的入口函数 ──

def get_vram_info() -> dict:
    """获取GPU显存信息 (树剪.py 启动入口兼容)"""
    info = get_nvidia_vram_info()
    return {
        "total_mb": info.get("total_mb", 0),
        "used_mb": info.get("used_mb", 0),
        "free_mb": info.get("free_mb", 0),
    }

def auto_init_gpu(enable_cudnn: bool = True) -> dict:
    """自动初始化GPU环境并返回报告 (树剪.py 启动入口)"""
    report = {
        "whisper_compute": "float16",
        "whisper_batch": 1,
        "cudnn_enabled": False,
    }

    vram = get_nvidia_vram_info()
    total_mb = vram.get("total_mb", 0)

    if total_mb > 0:
        # 根据显存自动选择计算精度
        if total_mb >= 8000:
            report["whisper_compute"] = "float16"
            report["whisper_batch"] = 4
        elif total_mb >= 4000:
            report["whisper_compute"] = "int8_float16"
            report["whisper_batch"] = 2
        else:
            report["whisper_compute"] = "int8"
            report["whisper_batch"] = 1

        if enable_cudnn:
            init_cuda_environment(enable_benchmark=True)
            report["cudnn_enabled"] = True

    logger.info(f"GPU初始化: 显存={total_mb}MB 已用={vram.get('used_mb', 0)}MB "
                f"Whisper={report['whisper_compute']} bs={report['whisper_batch']} "
                f"cudnn={'ON' if report['cudnn_enabled'] else 'OFF'}")

    return report
