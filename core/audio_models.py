"""
树剪 AI素材库 — 音频识别模型封装 (v11.0 强制双轨: SenseVoice + Whisper)
========================================================================
SenseVoice: 情绪识别 (7种) + 事件检测 (6种) + 多语言ASR
Whisper:    语音转文字 (large-v3)

两个模型同时运行，结果合并到 AudioResult。
无降级——任一模型不可用则抛出 RuntimeError。
"""
import os
import re
import tempfile
import logging
from pathlib import Path
from utils.silent_subprocess import run as _silent_run
from typing import Optional, List
from dataclasses import dataclass, field

_log = logging.getLogger("AudioModels")

PROJECT_ROOT = Path(__file__).parent.parent
SENSEVOICE_MODEL_DIR = PROJECT_ROOT / "models" / "SenseVoiceSmall"
# v12.0: 持久缓存目录 — 避免每次实例化都复制 ~900MB 模型到临时目录
_SENSEVOICE_CACHE = Path.home() / ".treecut" / "models" / "sensevoice"
_SENSEVOICE_CACHE.mkdir(parents=True, exist_ok=True)

SENSEVOICE_FIX = f"""
============================================================
  错误：SenseVoice 模型不可用
============================================================
  模型目录: {SENSEVOICE_MODEL_DIR}
  必需文件: model.pt (~893 MB)

  修复方法:
  1. pip install funasr modelscope torchaudio
  2. modelscope download --model FunAudioLLM/SenseVoiceSmall --local_dir {SENSEVOICE_MODEL_DIR}

  如果已有 model.pt 但 funasr 未安装:
  3. pip install funasr>=1.1.2
============================================================
"""

WHISPER_FIX = """
============================================================
  错误：Faster-Whisper 不可用
============================================================
  修复: pip install faster-whisper
============================================================
"""


@dataclass
class AudioResult:
    """音频识别统一结果 (v11.0 — 包含情绪+事件)"""
    # ── 语音转写 (Whisper) ──
    transcript: str = ""
    segments: List[dict] = field(default_factory=list)
    language: str = "zh"

    # ── 情绪识别 (SenseVoice) ──
    emotion: str = "neutral"                    # happy/sad/angry/neutral/fearful/disgusted/surprised
    emotion_confidence: float = 0.0

    # ── 事件检测 (SenseVoice) ──
    events: List[str] = field(default_factory=list)  # bgm/applause/laughter/cry/cough/sneeze

    # ── 启发式分类 (librosa — 辅助) ──
    has_music: bool = False
    has_laugh: bool = False
    has_speech: bool = False
    ambient_type: str = "silent"

    # ── 置信度 ──
    speech_confidence: float = 0.0
    audio_class_confidence: float = 0.0


# ═══════════════════════════════════════════
# 公共工具: 从视频提取音频
# ═══════════════════════════════════════════

def _extract_audio(video_path: str) -> Optional[str]:
    """提取视频音轨为临时WAV — 模块级公共函数"""
    try:
        tmp = tempfile.mktemp(suffix=".wav")
        _silent_run([
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", tmp
        ], capture_output=True, timeout=30)
        if os.path.exists(tmp):
            return tmp
        return None
    except Exception:
        return None


# ═══════════════════════════════════════════
# SenseVoice — 情绪 + 事件检测 (强制)
# ═══════════════════════════════════════════

class SenseVoiceEngine:
    """
    强制 SenseVoice 引擎 — 情绪 (7种) + 事件 (6种) + ASR
    若模型不可用则抛出 RuntimeError，不降级。
    """

    # SenseVoice 特殊 Token
    EMOTION_TOKENS = {
        "<|HAPPY|>": "happy", "<|SAD|>": "sad", "<|ANGRY|>": "angry",
        "<|NEUTRAL|>": "neutral", "<|FEARFUL|>": "fearful",
        "<|DISGUSTED|>": "disgusted", "<|SURPRISED|>": "surprised",
    }
    EVENT_TOKENS = {
        "<|bgm|>": "bgm", "<|applause|>": "applause",
        "<|laughter|>": "laughter", "<|cry|>": "cry",
        "<|cough|>": "cough", "<|sneeze|>": "sneeze",
    }
    LANGUAGE_TOKENS = {"<|zh|>", "<|en|>", "<|ja|>", "<|ko|>", "<|yue|>"}
    ITN_TOKENS = {"<|itn|>"}
    ALL_SPECIAL = EMOTION_TOKENS.keys() | EVENT_TOKENS.keys() | LANGUAGE_TOKENS | ITN_TOKENS

    def __init__(self, device: str = "cpu"):
        self.device = device
        self._model = None
        self._loaded = False
        self._tmp_model_dir = None

        if not SENSEVOICE_MODEL_DIR.exists():
            raise RuntimeError(
                f"SenseVoice 模型目录不存在: {SENSEVOICE_MODEL_DIR}\n{SENSEVOICE_FIX}"
            )

        model_pt = SENSEVOICE_MODEL_DIR / "model.pt"
        if not model_pt.exists():
            raise RuntimeError(
                f"SenseVoice 模型权重文件缺失: {model_pt}\n{SENSEVOICE_FIX}"
            )

        # funasr may fail with Chinese paths on Windows.
        # Workaround: copy model to ASCII temp dir if needed.
        try:
            from funasr import AutoModel
            model_path_str = str(SENSEVOICE_MODEL_DIR)
            print(f"   [SenseVoice] 加载模型 ({SENSEVOICE_MODEL_DIR})...")

            try:
                self._model = AutoModel(
                    model=model_path_str,
                    vad_model="fsmn-vad",
                    vad_kwargs={"max_single_segment_time": 30000},
                    device=self.device,
                    disable_update=True,
                )
            except Exception:
                # v12.0: 中文路径规避 — 使用持久缓存目录（不再每次复制到临时目录）
                import shutil as _shutil
                self._tmp_model_dir = str(_SENSEVOICE_CACHE)
                # 仅首次复制模型文件; 后续启动直接复用缓存
                if not (_SENSEVOICE_CACHE / "config.yaml").exists():
                    print(f"   [SenseVoice] 首次缓存模型到: {self._tmp_model_dir}")
                    for item in SENSEVOICE_MODEL_DIR.iterdir():
                        src = str(item)
                        dst = os.path.join(self._tmp_model_dir, item.name)
                        if item.is_file():
                            _shutil.copy2(src, dst)
                        elif item.is_dir() and not item.name.startswith('.') and not item.name.startswith('_'):
                            _shutil.copytree(src, dst, dirs_exist_ok=True,
                                            ignore=_shutil.ignore_patterns('.*', '__pycache__'))
                else:
                    print(f"   [SenseVoice] 使用缓存模型: {self._tmp_model_dir}")
                self._model = AutoModel(
                    model=self._tmp_model_dir,
                    vad_model="fsmn-vad",
                    vad_kwargs={"max_single_segment_time": 30000},
                    device=self.device,
                    disable_update=True,
                )

            self._loaded = True
            print(f"   [SenseVoice] 加载成功 (device={self.device})")

        except ImportError as e:
            raise RuntimeError(
                f"缺少 funasr 依赖: {e}\n请运行: pip install funasr>=1.1.2 modelscope torchaudio"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"SenseVoice 加载失败: {e}\n{SENSEVOICE_FIX}"
            ) from e

    @property
    def available(self) -> bool:
        return self._loaded and self._model is not None

    def __del__(self):
        # v12.0: 持久缓存目录不删除 — 下次启动直接复用
        # 只有旧版临时目录才需要清理
        if (self._tmp_model_dir and os.path.exists(self._tmp_model_dir)
                and 'sensevoice_' in self._tmp_model_dir  # 旧版 temp 前缀
                and '.treecut' not in self._tmp_model_dir):
            import shutil
            shutil.rmtree(self._tmp_model_dir, ignore_errors=True)

    def analyze(self, audio_path: str) -> dict:
        """
        分析音频 — 返回情绪 + 事件 + 文本
        {
          "text": "清洗后的转写文本",
          "emotion": "happy",
          "emotion_confidence": 0.92,
          "events": ["bgm", "laughter"],
          "language": "zh",
          "raw_text": "带特殊Token的原始输出"
        }
        """
        if not self.available:
            raise RuntimeError("SenseVoice 未初始化")

        try:
            result = self._model.generate(
                input=audio_path,
                cache={},
                language="auto",
                use_itn=True,
                batch_size_s=60,
                merge_vad=True,
                merge_length_s=15,
            )

            if not result or not isinstance(result, list):
                raise RuntimeError(f"SenseVoice 返回空结果: {result}")

            raw_text = result[0].get("text", "")

            # 解析特殊 Token
            emotion = "neutral"
            events = []
            language = "zh"

            for tok_full, emotion_name in self.EMOTION_TOKENS.items():
                if tok_full in raw_text:
                    emotion = emotion_name
                    break

            for tok_full, event_name in self.EVENT_TOKENS.items():
                if tok_full in raw_text:
                    events.append(event_name)

            for lang_tok in self.LANGUAGE_TOKENS:
                if lang_tok in raw_text:
                    language = lang_tok.strip("<>|").split("|")[0]
                    break

            # 清洗文本 (移除所有特殊Token)
            clean_text = self._clean_text(raw_text)

            return {
                "text": clean_text,
                "emotion": emotion,
                "emotion_confidence": 0.85,  # SenseVoice 不单独输出置信度
                "events": events,
                "language": language,
                "raw_text": raw_text,
            }

        except Exception as e:
            raise RuntimeError(f"SenseVoice 推理失败: {e}") from e

    def _clean_text(self, raw: str) -> str:
        """移除 SenseVoice 特殊 Token，保留纯文本"""
        text = raw
        for tok in self.ALL_SPECIAL:
            text = text.replace(tok, "")
        # 移除多余空格
        text = re.sub(r'\s+', ' ', text).strip()
        return text


# ═══════════════════════════════════════════
# Whisper — 语音转文字 (强制)
# ═══════════════════════════════════════════

class WhisperModel:
    """Faster-Whisper large-v3 — 强制语音转文字，不可用即抛异常"""

    def __init__(self, model_size: str = "large-v3", device: str = "cpu",
                 compute_type: str = "int8"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None
        self._loaded = False

    def _lazy_load(self):
        if self._loaded:
            return
        try:
            from faster_whisper import WhisperModel as FWModel
            print(f"   [Whisper] 加载 {self.model_size} ({self.device}, {self.compute_type})...")
            self._model = FWModel(self.model_size, device=self.device,
                                  compute_type=self.compute_type)
            self._loaded = True
            print(f"   [Whisper] 加载成功")
        except ImportError:
            raise RuntimeError(
                f"faster-whisper 未安装\n{WHISPER_FIX}"
            )
        except Exception as e:
            raise RuntimeError(
                f"Whisper 模型加载失败: {e}\n{WHISPER_FIX}"
            ) from e

    @property
    def available(self) -> bool:
        return self._loaded and self._model is not None

    def transcribe(self, video_path: str) -> AudioResult:
        """提取音频并转写 — v14.0: 增加缓存支持"""
        result = AudioResult()

        if not self.available:
            self._lazy_load()
        if not self.available:
            raise RuntimeError("Whisper 模型未加载")

        # ★ v14.0: 缓存检查
        try:
            from utils.cache_manager import get_cache_manager
            cm = get_cache_manager()
            cached = cm.get(video_path, "whisper_transcribe")
            if cached:
                result.segments = cached.get("segments", [])
                result.transcript = cached.get("transcript", "")
                result.language = cached.get("language", "zh")
                result.has_speech = len(result.segments) > 0
                _log.info(f"Whisper转写命中缓存: {len(result.segments)}段")
                return result
        except ImportError:
            pass

        audio_path = _extract_audio(video_path)
        if not audio_path:
            raise RuntimeError(
                f"无法从视频提取音频: {video_path}\n"
                f"请确认 ffmpeg 已安装并可用。"
            )

        try:
            segments, info = self._model.transcribe(audio_path, beam_size=5, language="zh")
            segs = []
            texts = []
            for seg in segments:
                segs.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
                texts.append(seg.text.strip())
            result.segments = segs
            result.transcript = " ".join(texts)
            result.language = info.language
            result.speech_confidence = info.language_probability
            result.has_speech = len(texts) > 0

            # ★ v14.0: 写入缓存
            try:
                from utils.cache_manager import get_cache_manager
                cm = get_cache_manager()
                cm.set(video_path, "whisper_transcribe", {
                    "segments": segs, "transcript": result.transcript,
                    "language": result.language,
                })
            except ImportError:
                pass
        except Exception as e:
            error_msg = str(e)
            # ★ v14.1: OOM自动降级重试
            if ("out of memory" in error_msg.lower() or "cuda" in error_msg.lower()):
                _log.warning(f"Whisper OOM/GPU错误，尝试INT8降级重试... ({error_msg[:80]})")
                try:
                    from utils.vram_manager import check_vram
                    # 切换为最轻量化模式
                    self._model = FWModel(self.model_size, device=self.device,
                                          compute_type="int8", cpu_threads=4)
                    segments, info = self._model.transcribe(audio_path, beam_size=3, language="zh",
                                                            vad_filter=True)
                    segs2, texts2 = [], []
                    for seg in segments:
                        segs2.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
                        texts2.append(seg.text.strip())
                    result.segments = segs2
                    result.transcript = " ".join(texts2)
                    result.language = info.language
                    result.has_speech = len(texts2) > 0
                    _log.info(f"降级Whisper完成: {len(segs2)}段 (INT8模式)")
                except Exception as e2:
                    raise RuntimeError(f"Whisper降级重试也失败: {e2}") from e2
            else:
                raise RuntimeError(f"Whisper 转写失败: {e}") from e
        finally:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)

        return result


# ═══════════════════════════════════════════
# AudioClassifier — librosa 启发式 (辅助)
# ═══════════════════════════════════════════

class AudioClassifier:
    """音频分类器 — 启发式音乐/语音/笑声检测 (辅助 SenseVoice)"""

    def __init__(self):
        self._librosa = None
        self._np = None
        try:
            import librosa
            import numpy as np
            self._librosa = librosa
            self._np = np
        except ImportError:
            pass

    def classify(self, video_path: str, audio_path: str = None) -> dict:
        result = {"has_music": False, "has_laugh": False, "has_speech": False,
                  "ambient_type": "silent", "confidence": 0.0}

        if not self._librosa:
            return result

        target = audio_path or _extract_audio(video_path)
        if not target or not os.path.exists(target):
            return result

        try:
            y, sr = self._librosa.load(target, sr=22050, duration=30)
            rms = self._librosa.feature.rms(y=y)[0]
            energy = float(self._np.mean(rms))

            if energy < 0.01:
                result["ambient_type"] = "silent"
                return result

            spectral_centroid = self._librosa.feature.spectral_centroid(y=y, sr=sr)[0]
            centroid_mean = float(self._np.mean(spectral_centroid))
            mfcc = self._librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
            mfcc_std = float(self._np.std(mfcc))
            zcr = self._librosa.feature.zero_crossing_rate(y)[0]
            zcr_mean = float(self._np.mean(zcr))

            if centroid_mean > 2000 and mfcc_std > 20:
                result["has_music"] = True
                result["ambient_type"] = "music"
                result["confidence"] = 0.7
            elif zcr_mean > 0.05 and energy > 0.05:
                result["has_speech"] = True
                result["ambient_type"] = "speech"
                result["confidence"] = 0.6

            if result["has_music"] and result["has_speech"]:
                result["ambient_type"] = "mixed"

            if self._has_laugh_pattern(y, sr):
                result["has_laugh"] = True
        except Exception as _e:
            from utils.logging import log_warning
            log_warning('audio_models', str(_e)[:80])
        finally:
            if audio_path is None and os.path.exists(target):
                os.remove(target)

        return result

    def _has_laugh_pattern(self, y, sr) -> bool:
        try:
            hop = int(sr * 0.05)
            chunks = [y[i:i + hop] for i in range(0, len(y) - hop, hop)]
            rms_vals = [float(self._np.sqrt(self._np.mean(c**2))) for c in chunks if len(c) > 0]
            if len(rms_vals) < 10:
                return False
            spikes = sum(1 for r in rms_vals if r > self._np.mean(rms_vals) * 3)
            return spikes >= 3
        except Exception:
            return False


# ═══════════════════════════════════════════
# 统一音频分析入口 (SenseVoice + Whisper 双轨)
# ═══════════════════════════════════════════

class UnifiedAudioAnalyzer:
    """
    统一音频分析 — 同时运行 SenseVoice (情绪+事件) + Whisper (转写)

    无降级：两个模型都必须可用。
    """

    def __init__(self):
        self._sensevoice = None
        self._whisper = None
        self._classifier = None

    @property
    def sensevoice(self):
        if self._sensevoice is None:
            self._sensevoice = SenseVoiceEngine()
        return self._sensevoice

    @property
    def whisper(self):
        if self._whisper is None:
            self._whisper = WhisperModel()
        return self._whisper

    @property
    def classifier(self):
        if self._classifier is None:
            self._classifier = AudioClassifier()
        return self._classifier

    def analyze(self, video_path: str) -> AudioResult:
        """
        完整音频分析 — SenseVoice + Whisper 并行

        1. 提取音频轨道
        2. SenseVoice: 情绪 + 事件 + ASR文本
        3. Whisper: 精准转写 + 时间戳
        4. AudioClassifier: 辅助启发式
        5. 合并结果
        """
        audio_path = _extract_audio(video_path)
        if not audio_path:
            raise RuntimeError(f"无法从视频提取音频: {video_path}")

        try:
            # ── SenseVoice (情绪 + 事件) ──
            sv_result = {}
            try:
                sv_result = self.sensevoice.analyze(audio_path)
            except Exception as e:
                raise RuntimeError(f"SenseVoice 分析失败: {e}") from e

            # ── Whisper (精准转写) ──
            whisper_result = self.whisper.transcribe(video_path)

            # ── AudioClassifier (辅助) ──
            clf_result = self.classifier.classify(video_path, audio_path=audio_path)

            # ── 合并结果 ──
            result = AudioResult()

            # Whisper 转写
            result.transcript = whisper_result.transcript
            result.segments = whisper_result.segments
            result.language = whisper_result.language
            result.speech_confidence = whisper_result.speech_confidence
            result.has_speech = whisper_result.has_speech

            # SenseVoice 情绪+事件 (可能因依赖缺失而为空)
            if sv_result:
                result.emotion = sv_result.get("emotion", "neutral")
                result.emotion_confidence = sv_result.get("emotion_confidence", 0.0)
                result.events = sv_result.get("events", [])
                # 如果 SenseVoice 有转写且 Whisper 没有，用 SenseVoice 的
                if not result.transcript and sv_result.get("text"):
                    result.transcript = sv_result["text"]

            # 辅助分类
            result.has_music = clf_result.get("has_music", False)
            result.has_laugh = clf_result.get("has_laugh", False)
            result.ambient_type = clf_result.get("ambient_type", "silent")
            result.audio_class_confidence = clf_result.get("confidence", 0.0)

            return result

        finally:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
