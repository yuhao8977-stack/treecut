"""
树剪 TreeCut v11.1 — 统一模型调度器 (Orchestrator)
================================================================
强制模型 — 无降级。所有 AI 模型由本模块统一加载、调用、健康检查、结果记录。

加载失败 → RuntimeError + 详细修复指南。不尝试任何备用模型。

用法:
  from core.orchestrator import orch
  result = orch.analyze_image(image_path)
  audio  = orch.analyze_audio(video_path)
  clips  = orch.match_clips(copy_text, num_clips=8)
"""
import os
import time
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any

PROJECT_ROOT = Path(__file__).parent.parent
MODELS_DIR = PROJECT_ROOT / "models"

FIX_QWEN3 = """
[FIX] Qwen3-VL-4B 模型不可用:
  pip install huggingface_hub
  python -c "from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen3-VL-4B-Instruct-FP8', local_dir='models/Qwen3-VL-4B-Instruct-FP8')"
"""

FIX_SENSEVOICE = """
[FIX] SenseVoice 模型不可用:
  pip install funasr>=1.1.2 modelscope torchaudio
  modelscope download --model FunAudioLLM/SenseVoiceSmall --local_dir models/SenseVoiceSmall
"""

FIX_WHISPER = """
[FIX] Whisper 模型不可用:
  pip install faster-whisper
"""

FIX_FAISS = """
[FIX] FAISS 索引不可用:
  python -c "from core.library_builder import LibraryBuilder; LibraryBuilder().build_faiss_index()"
"""


class Orchestrator:
    """统一模型调度器 — 线程安全单例，强制加载"""

    _instance: Optional["Orchestrator"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._vision = None
        self._sensevoice = None
        self._whisper = None
        self._audio_classifier = None
        self._kb = None
        self._matcher = None
        self._loaded = False
        self._load_time = 0.0

    # ═══════════════════ 强制加载 ═══════════════════

    def load_all(self):
        """强制加载所有模型。任一失败 → RuntimeError。"""
        print("[Orchestrator] 加载所有模型...")
        t0 = time.time()

        errors = []

        # Vision
        try:
            self._load_vision()
        except Exception as e:
            errors.append(f"视觉模型: {e}")

        # SenseVoice
        try:
            self._load_sensevoice()
        except Exception as e:
            errors.append(f"SenseVoice: {e}")

        # Whisper
        try:
            self._load_whisper()
        except Exception as e:
            errors.append(f"Whisper: {e}")

        # KnowledgeBridge
        try:
            self._load_knowledge()
        except Exception as e:
            errors.append(f"KnowledgeBridge: {e}")

        # SmartMatcher (FAISS)
        try:
            self._load_matcher()
        except Exception as e:
            errors.append(f"FAISS: {e}")

        if errors:
            raise RuntimeError(
                "模型加载失败:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        self._loaded = True
        self._load_time = time.time() - t0
        print(f"[Orchestrator] 全部模型加载完成 ({self._load_time:.0f}s)")

    # ═══════════════════ 各模型加载 ═══════════════════

    def _load_vision(self):
        model_dir = MODELS_DIR / "Qwen3-VL-4B-Instruct-FP8"
        if not model_dir.exists():
            raise RuntimeError(f"Qwen3-VL-4B 模型目录不存在: {model_dir}\n{FIX_QWEN3}")
        sft = list(model_dir.glob("*.safetensors"))
        if not sft:
            raise RuntimeError(f"Qwen3-VL-4B 无权重文件: {model_dir}\n{FIX_QWEN3}")

        import torch
        from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

        print(f"  [Vision] Qwen3-VL-4B ({model_dir})...")
        dt = torch.float16 if torch.cuda.is_available() else torch.float32
        self._vision_processor = AutoProcessor.from_pretrained(str(model_dir), trust_remote_code=True)
        self._vision = Qwen3VLForConditionalGeneration.from_pretrained(
            str(model_dir), device_map="auto", trust_remote_code=True,
            torch_dtype=dt, offload_folder=str(MODELS_DIR / ".offload"))

    def _load_sensevoice(self):
        model_dir = MODELS_DIR / "SenseVoiceSmall"
        if not (model_dir / "model.pt").exists():
            raise RuntimeError(f"SenseVoice 权重缺失: {model_dir}\n{FIX_SENSEVOICE}")

        from funasr import AutoModel
        print(f"  [SenseVoice] ({model_dir})...")
        # 中文路径 workaround
        try:
            self._sensevoice = AutoModel(model=str(model_dir), vad_model="fsmn-vad",
                vad_kwargs={"max_single_segment_time": 30000}, device="cpu", disable_update=True)
        except Exception:
            import shutil, tempfile
            tmp = tempfile.mkdtemp(prefix="sv_")
            for item in model_dir.iterdir():
                if item.is_file():
                    shutil.copy2(str(item), os.path.join(tmp, item.name))
            self._sensevoice = AutoModel(model=tmp, vad_model="fsmn-vad",
                vad_kwargs={"max_single_segment_time": 30000}, device="cpu", disable_update=True)

    def _load_whisper(self):
        from faster_whisper import WhisperModel as FWModel
        print("  [Whisper] large-v3 (cpu, int8)...")
        self._whisper = FWModel("large-v3", device="cpu", compute_type="int8")

    def _load_knowledge(self):
        from utils.knowledge import get_bridge
        self._kb = get_bridge()

    def _load_matcher(self):
        from core.smart_matcher_v3 import get_smart_matcher
        self._matcher = get_smart_matcher()
        self._matcher._lazy_load()

    # ═══════════════════ 推理 API ═══════════════════

    def analyze_image(self, image_path: str) -> dict:
        """视觉分析 → {caption, objects, materials, colors, style}"""
        if not self._vision:
            raise RuntimeError("VisionModel 未加载。请先调用 orchestrator.load_all()")

        from PIL import Image
        image = Image.open(image_path).convert("RGB")
        messages = [{"role": "user", "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": "描述这个画面中的物体、材质、颜色和风格。用中文简短回答，逗号分隔。"},
        ]}]
        prompt = self._vision_processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self._vision_processor(text=prompt, images=[image], return_tensors="pt").to(self._vision.device)
        out = self._vision.generate(**inputs, max_new_tokens=128)
        text = self._vision_processor.decode(out[0], skip_special_tokens=True)
        if "assistant" in text:
            text = text.split("assistant")[-1].strip()

        res = {"caption": text, "objects": [], "materials": [], "colors": [], "style": ""}
        for p in text.replace("，", ",").split(","):
            p = p.strip()
            if not p: continue
            if any(k in p for k in ["岛台","抽屉","烤箱","插座","水槽","灯带","冰箱","拉篮","餐桌","吧台","柜"]):
                res["objects"].append(p)
            if any(k in p for k in ["岩板","石","木","钢","玻璃","水泥","不锈钢","亚克力","微水泥","洞石"]):
                res["materials"].append(p)
            if any(k in p for k in ["白","黑","灰","棕","米","蓝","绿","红","金","银","奶","原木"]):
                res["colors"].append(p)
            if any(k in p for k in ["风","简约","现代","复古","侘寂","轻奢","工业","北欧","中式","原木"]):
                if not res["style"]: res["style"] = p

        from core.database import db
        db.record_model_call("Qwen3-VL-4B", call_type="analyze_image", input_summary=os.path.basename(image_path),
                             output_summary=text[:100])
        return res

    def analyze_audio(self, video_path: str) -> dict:
        """音频分析 → {transcript, emotion, events, segments}"""
        if not self._whisper: raise RuntimeError("Whisper 未加载")

        import tempfile
        from utils.silent_subprocess import run as _silent_run

        tmp = tempfile.mktemp(suffix=".wav")
        _silent_run(["ffmpeg","-y","-i",video_path,"-vn","-acodec","pcm_s16le","-ar","16000","-ac","1",tmp],
                     capture_output=True, timeout=30)

        segments, info = self._whisper.transcribe(tmp, beam_size=5, language="zh")
        segs = [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments]
        transcript = " ".join(s["text"] for s in segs)

        # SenseVoice
        emotion, events = "neutral", []
        if self._sensevoice:
            try:
                sv = self._sensevoice.generate(input=tmp, cache={}, language="auto", use_itn=True,
                                                batch_size_s=60, merge_vad=True, merge_length_s=15)
                raw = sv[0].get("text", "") if sv else ""
                for tok, em in {"<|HAPPY|>":"happy","<|SAD|>":"sad","<|ANGRY|>":"angry","<|NEUTRAL|>":"neutral"}.items():
                    if tok in raw: emotion = em; break
                for tok, ev in {"<|bgm|>":"bgm","<|applause|>":"applause","<|laughter|>":"laughter",
                                 "<|cry|>":"cry","<|cough|>":"cough","<|sneeze|>":"sneeze"}.items():
                    if tok in raw: events.append(ev)
            except Exception:
                pass

        if os.path.exists(tmp): os.remove(tmp)

        from core.database import db
        db.record_model_call("Whisper+SenseVoice", call_type="analyze_audio", input_summary=video_path[:80],
                             output_summary=transcript[:100])
        return {"transcript": transcript, "segments": segs, "emotion": emotion, "events": events,
                "language": info.language, "has_speech": len(segs) > 0}

    def match_clips(self, copy_text: str, num_clips: int = 8) -> List[Dict]:
        """智能素材匹配"""
        if not self._matcher: raise RuntimeError("SmartMatcher 未加载")
        results = self._matcher.search_by_copy(copy_text, num_clips)
        from core.database import db
        db.record_model_call("SmartMatcher", call_type="match_clips", input_summary=copy_text[:80],
                             output_summary=f"{len(results)} clips")
        return results

    def health_check(self) -> Dict[str, bool]:
        """返回所有模型健康状态"""
        return {
            "vision": self._vision is not None,
            "sensevoice": self._sensevoice is not None,
            "whisper": self._whisper is not None,
            "knowledge_bridge": self._kb is not None,
            "smart_matcher": self._matcher is not None,
        }

    def get_status_report(self) -> str:
        checks = self.health_check()
        lines = ["模型状态:"]
        for name, ok in checks.items():
            lines.append(f"  {'[OK]' if ok else '[FAIL]'} {name}")
        return "\n".join(lines)


# ── 全局单例 ──
orch = Orchestrator()
