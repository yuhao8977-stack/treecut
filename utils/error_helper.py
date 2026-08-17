"""
树剪 TreeCut v11.1 — 统一错误诊断助手
================================================================
根据异常信息自动识别常见错误类型，弹出修复指引对话框。

用法:
  from utils.error_helper import handle_error
  try:
      ...
  except Exception as e:
      handle_error(e, parent=root)
"""
import sys
import traceback
from typing import Optional

ERROR_MAP = {
    "DEEPSEEK_API_KEY": {
        "code": "E002", "title": "DeepSeek API Key 未配置",
        "msg": "DeepSeek API Key 无效或未配置，文案生成将使用模板备用。",
        "fix": "打开【系统设置】→ AI模型配置 → 输入正确的 API Key → 保存配置",
        "level": "warn",
    },
    "openai": {
        "code": "E001", "title": "openai 库未安装",
        "msg": "调用 DeepSeek API 需要 openai 库。",
        "fix": "pip install openai>=1.0.0",
        "level": "error",
    },
    "Qwen3-VL-4B": {
        "code": "E003", "title": "Qwen3-VL-4B 视觉模型缺失",
        "msg": "本地视觉模型文件未找到或加载失败。",
        "fix": "pip install huggingface_hub\npython -c \"from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen3-VL-4B-Instruct-FP8', local_dir='models/Qwen3-VL-4B-Instruct-FP8')\"",
        "level": "error",
    },
    "SenseVoice": {
        "code": "E004", "title": "SenseVoice 模型不可用",
        "msg": "SenseVoice 情绪识别模型加载失败。",
        "fix": "pip install funasr>=1.1.2 modelscope torchaudio\nmodelscope download --model FunAudioLLM/SenseVoiceSmall --local_dir models/SenseVoiceSmall",
        "level": "error",
    },
    "faster.whisper|faster_whisper|Whisper": {
        "code": "E005", "title": "Whisper 语音识别不可用",
        "msg": "faster-whisper 库未安装或模型加载失败。",
        "fix": "pip install faster-whisper",
        "level": "error",
    },
    "faiss": {
        "code": "E006", "title": "FAISS 向量检索不可用",
        "msg": "FAISS 索引不存在或损坏。",
        "fix": "python force_rebuild_faiss.py",
        "level": "error",
    },
    "SmartMatcher": {
        "code": "E007", "title": "智能匹配引擎不可用",
        "msg": "SmartMatcher 加载失败，素材匹配将降级。",
        "fix": "python force_rebuild_faiss.py\n检查 material_engine_v3/core/smart_matcher.py 是否存在",
        "level": "warn",
    },
    "edge.tts|edge_tts": {
        "code": "E008", "title": "TTS 配音引擎不可用",
        "msg": "edge-tts 库未安装。",
        "fix": "pip install edge-tts>=6.0.0",
        "level": "warn",
    },
    "pyJianYingDraft": {
        "code": "E009", "title": "剪映草稿生成库缺失",
        "msg": "pyJianYingDraft 未安装，无法生成剪映草稿。",
        "fix": "从本地安装 pyJianYingDraft 包",
        "level": "error",
    },
    "ffmpeg|ffprobe": {
        "code": "E010", "title": "FFmpeg 未安装",
        "msg": "视频处理需要 FFmpeg 工具。",
        "fix": "下载 FFmpeg: https://ffmpeg.org/download.html\n将 ffmpeg.exe 放入系统 PATH",
        "level": "error",
    },
    "torch|transformers|Pillow": {
        "code": "E011", "title": "核心依赖缺失",
        "msg": "PyTorch/Transformers/Pillow 等核心包未安装。",
        "fix": "pip install torch transformers Pillow",
        "level": "error",
    },
    "sentence.transformers|sentence_transformers|BGE": {
        "code": "E012", "title": "文本嵌入模型不可用",
        "msg": "sentence-transformers 库未安装。",
        "fix": "pip install sentence-transformers>=2.5.0",
        "level": "error",
    },
    "Z:\\\\|Z盘|Z驱": {
        "code": "E013", "title": "素材路径 (Z盘) 不存在",
        "msg": "默认素材路径指向 Z:\\ 盘，但当前系统不存在该盘符。",
        "fix": "打开【系统设置】→ 修改素材路径为实际文件夹\n或设置环境变量: TREECUT_SELLING_DIR=你的素材目录",
        "level": "warn",
    },
    "models\\\\Qwen|模型目录不存在": {
        "code": "E014", "title": "模型目录不存在",
        "msg": "本地 AI 模型文件未找到。",
        "fix": "检查 models/ 目录是否存在对应模型文件夹\n运行 dl_model.bat 下载视觉模型",
        "level": "error",
    },
}


def diagnose_error(error_str: str) -> Optional[dict]:
    """根据错误字符串匹配已知错误类型"""
    import re
    for pattern, info in ERROR_MAP.items():
        if re.search(pattern, error_str, re.IGNORECASE):
            return info
    return None


def handle_error(e: Exception, parent=None, log_callback=None):
    """
    统一错误处理入口。
    根据异常信息匹配已知错误 → 弹窗显示修复指引 → 写入日志。
    """
    error_str = str(e)
    traceback_str = traceback.format_exc()

    # 记录日志
    if log_callback:
        log_callback(f"[ERROR] {type(e).__name__}: {error_str[:200]}")
    else:
        print(f"[ERROR] {type(e).__name__}: {error_str[:200]}")

    # 诊断
    info = diagnose_error(error_str)
    if not info:
        # 也检查 traceback
        info = diagnose_error(traceback_str)

    from tkinter import messagebox

    if info:
        level = info.get("level", "error")
        if level == "warn":
            messagebox.showwarning(
                f"警告 {info['code']} — {info['title']}",
                f"{info['msg']}\n\n修复方法:\n{info['fix']}\n\n技术细节:\n{error_str[:300]}",
                parent=parent,
            )
        else:
            messagebox.showerror(
                f"错误 {info['code']} — {info['title']}",
                f"{info['msg']}\n\n修复方法:\n{info['fix']}\n\n技术细节:\n{error_str[:300]}",
                parent=parent,
            )
    else:
        # 未知错误
        messagebox.showerror(
            "未知错误",
            f"程序遇到未识别的错误:\n\n{error_str[:500]}\n\n"
            "请将以下信息截图并反馈给开发者。",
            parent=parent,
        )
        traceback.print_exc()


def diagnose_and_log(e: Exception, logger=None) -> str:
    """诊断错误并返回可读的修复建议（不弹窗）。用于非 GUI 场景。"""
    info = diagnose_error(str(e))
    if info:
        msg = f"[{info['code']}] {info['title']}\n修复: {info['fix']}"
    else:
        msg = f"[UNKNOWN] {e}"
    if logger:
        logger(msg)
    return msg
