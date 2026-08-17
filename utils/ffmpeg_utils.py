"""
FFmpeg工具集 - 视频信息提取、关键帧导出、硬解码参数
"""
import os
import subprocess
import json
from utils.logging import get_loguru_logger as get_logger
logger = get_logger("ffmpeg")
def get_video_info(video_path: str) -> dict:
    """使用ffprobe获取视频完整元数据"""
    if not os.path.exists(video_path):
        logger.error(f"视频文件不存在: {video_path}")
        return {}
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, encoding="utf-8")
        if result.returncode != 0:
            logger.error(f"ffprobe失败: {result.stderr[:200]}")
            return {}
        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        video_stream = None
        audio_stream = None
        for s in data.get("streams", []):
            if s.get("codec_type") == "video" and video_stream is None:
                video_stream = s
            elif s.get("codec_type") == "audio" and audio_stream is None:
                audio_stream = s
        if video_stream is None:
            logger.error("未找到视频流")
            return {}
        # 解析帧率
        fps = 0
        r_frame_rate = video_stream.get("r_frame_rate", "0/1")
        if "/" in r_frame_rate:
            num, den = r_frame_rate.split("/")
            if float(den) > 0:
                fps = round(float(num) / float(den), 2)
        info = {
            "duration": float(fmt.get("duration", 0)),
            "width": int(video_stream.get("width", 0)),
            "height": int(video_stream.get("height", 0)),
            "resolution": f"{video_stream.get('width', 0)}x{video_stream.get('height', 0)}",
            "fps": fps,
            "codec": video_stream.get("codec_name", ""),
            "bitrate": int(fmt.get("bit_rate", 0)),
            "has_audio": audio_stream is not None,
        }
        return info
    except subprocess.TimeoutExpired:
        logger.error(f"ffprobe超时: {video_path}")
        return {}
    except json.JSONDecodeError:
        logger.error("ffprobe输出JSON解析失败")
        return {}
    except Exception as e:
        logger.error(f"获取视频信息失败: {e}")
        return {}
def extract_frame(video_path: str, time_sec: float, output_path: str) -> bool:
    """提取指定时间点的关键帧为JPG"""
    try:
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(time_sec),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, encoding="utf-8")
        if result.returncode == 0 and os.path.exists(output_path):
            return True
        logger.debug(f"关键帧提取失败: {result.stderr[:100]}")
        return False
    except Exception as e:
        logger.error(f"提取关键帧异常: {e}")
        return False
def extract_audio(video_path: str, output_path: str, sample_rate: int = 16000) -> bool:
    """从视频提取单声道16kHz WAV音频"""
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", str(sample_rate),
            "-ac", "1",
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, encoding="utf-8")
        return result.returncode == 0
    except Exception as e:
        logger.error(f"音频提取异常: {e}")
        return False
