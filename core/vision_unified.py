"""
树剪 — 统一视觉模型接口 (强制 Qwen3-VL-4B, 无降级)
========================================================================
v11.0: 删除所有降级逻辑。仅加载 Qwen3-VL-4B。
       若加载失败则抛出 RuntimeError，禁止回退到其他模型。
       用法: from core.vision_unified import VisionModel; m=VisionModel(); m.analyze(img)
"""
import os
import sys
import json as _json
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent
MODELS_DIR = PROJECT_ROOT / "models"

# ── 唯一强制模型 ──
FORCE_MODEL_KEY = "qwen3-4b"
FORCE_MODEL_HF = "Qwen/Qwen3-VL-4B-Instruct-FP8"
FORCE_MODEL_DIR = os.environ.get("TREECUT_VISION_MODEL_DIR", "Qwen3-VL-4B-Instruct-FP8")
FORCE_MODEL_DIR_FULL = MODELS_DIR / FORCE_MODEL_DIR

FIX_INSTRUCTIONS = f"""
============================================================
  错误：Qwen3-VL-4B 视觉模型不可用
============================================================
  模型目录: {FORCE_MODEL_DIR_FULL}
  必需文件: *.safetensors (约 5.6 GB)

  修复方法:
  1. 从 HuggingFace 下载:
     pip install huggingface_hub
     python -c "from huggingface_hub import snapshot_download; \\
       snapshot_download('{FORCE_MODEL_HF}', local_dir='{FORCE_MODEL_DIR_FULL}')"

  2. 或从 ModelScope 下载:
     pip install modelscope
     modelscope download --model {FORCE_MODEL_HF} --local_dir {FORCE_MODEL_DIR_FULL}

  3. 确认文件存在后重新启动程序。
============================================================
"""


class VisionModel:
    """
    强制 Qwen3-VL-4B 视觉模型 (v11.0 — 无降级)

    若模型目录不存在或加载失败，直接抛出 RuntimeError。
    不尝试 Ollama、Florence 或任何其他备选。
    """

    def __init__(self):
        import os as _vm_os
        if _vm_os.environ.get("TREECUT_SKIP_VISION", "").lower() == "true":
            print("   [Vision] TREECUT_SKIP_VISION=true，跳过视觉模型加载")
            self.model_key = FORCE_MODEL_KEY
            self._model = None
            self._processor = None
            self._type = None
            self._loaded = "skipped"
            return

        self.model_key = FORCE_MODEL_KEY
        self._model = None
        self._processor = None
        self._type = "transformers"
        self._loaded = None

        # ── 第一步：检查模型目录是否存在 ──
        if not FORCE_MODEL_DIR_FULL.exists():
            raise RuntimeError(
                f"Qwen3-VL-4B 模型目录不存在: {FORCE_MODEL_DIR_FULL}\n"
                f"{FIX_INSTRUCTIONS}"
            )

        safetensors = list(FORCE_MODEL_DIR_FULL.glob("*.safetensors"))
        bins = list(FORCE_MODEL_DIR_FULL.glob("*.bin"))
        if not safetensors and not bins:
            raise RuntimeError(
                f"Qwen3-VL-4B 模型目录无权重文件: {FORCE_MODEL_DIR_FULL}\n"
                f"  找到的文件: {list(FORCE_MODEL_DIR_FULL.glob('*'))}\n"
                f"{FIX_INSTRUCTIONS}"
            )

        # ── 第二步：加载模型 ──
        self._load_model()

    def _load_model(self):
        """加载 Qwen3-VL-4B — 带重试+独立offload目录+清理"""
        local_path = FORCE_MODEL_DIR_FULL
        last_error = None

        for attempt in range(3):
            try:
                import gc
                import torch
                import json
                import tempfile
                import shutil
                from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

                # 每次尝试前清理GPU/CPU内存
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

                print(f"   [Vision] 加载 Qwen3-VL-4B ({local_path})... 尝试 {attempt+1}/3")

                self._processor = AutoProcessor.from_pretrained(
                    str(local_path), trust_remote_code=True
                )

                dt = torch.float16 if torch.cuda.is_available() else torch.float32
                with open(str(local_path / 'config.json')) as _f:
                    cfg = json.load(_f)
                arch = cfg.get('architectures', [''])[0]

                if 'Qwen3VL' not in arch:
                    raise RuntimeError(
                        f"模型架构不匹配: 期望 Qwen3VL, 实际 {arch}\n"
                        f"请确认目录 {local_path} 包含正确模型文件。"
                    )

                # 使用进程唯一的offload目录，避免跨进程文件锁冲突
                base_offload = str(PROJECT_ROOT / 'models' / '.offload')
                pid_offload = os.path.join(base_offload, f"pid_{os.getpid()}")
                # 清理上次失败的残留
                if os.path.exists(pid_offload):
                    shutil.rmtree(pid_offload, ignore_errors=True)
                os.makedirs(pid_offload, exist_ok=True)

                # 仅清理PID专属offload目录，不再删除共享目录中其他进程的文件
                # （原代码 glob("*.safetensors") 会误删其他进程正在使用的权重文件）

                self._model = Qwen3VLForConditionalGeneration.from_pretrained(
                    str(local_path),
                    device_map='auto',
                    trust_remote_code=True,
                    torch_dtype=dt,
                    offload_folder=pid_offload,
                )

                self._loaded = FORCE_MODEL_DIR
                print(f"   [Vision] Qwen3-VL-4B 加载成功 (device={self._model.device})")
                return  # 成功，退出

            except (OSError, RuntimeError) as e:
                last_error = e
                err_msg = str(e)
                # safetensors I/O error 1224: 文件映射冲突 → 重试
                if "error 1224" in err_msg or "Error while serializing" in err_msg:
                    print(f"   [Vision] offload冲突 (I/O 1224), 清理后重试...")
                    # 仅清理本进程的offload目录，不影响其他进程
                    try:
                        if os.path.exists(pid_offload):
                            shutil.rmtree(pid_offload, ignore_errors=True)
                            os.makedirs(pid_offload, exist_ok=True)
                    except Exception:
                        pass
                    import time
                    time.sleep(2)  # 等文件系统释放锁
                    continue
                # 其他OS错误也重试
                elif "No space left" in err_msg:
                    print(f"   [Vision] 磁盘空间不足, 清理offload...")
                    try:
                        shutil.rmtree(base_offload, ignore_errors=True)
                        os.makedirs(base_offload, exist_ok=True)
                    except Exception:
                        pass
                    continue
                else:
                    break  # 未知错误，不重试

            except ImportError as e:
                raise RuntimeError(
                    f"缺少依赖包: {e}\n"
                    f"请运行: pip install torch transformers Pillow"
                ) from e
            except Exception as e:
                last_error = e
                if attempt < 2:
                    print(f"   [Vision] 加载异常, 2s后重试: {e}")
                    import time
                    time.sleep(2)
                    continue
                break

        raise RuntimeError(
            f"Qwen3-VL-4B 加载失败 (3次尝试): {last_error}\n"
            f"模型目录: {local_path}\n"
            f"{FIX_INSTRUCTIONS}"
        ) from last_error

    @property
    def available(self) -> bool:
        return self._model is not None

    def analyze(self, image_path: str) -> dict:
        """分析画面 — 返回 {caption, objects, materials, colors, style}"""
        if not self._model:
            raise RuntimeError("VisionModel 未初始化，请检查 Qwen3-VL-4B 模型")

        try:
            from PIL import Image
            image = Image.open(image_path).convert("RGB")

            # Qwen3-VL requires chat-format input (text + image)
            messages = [{
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": "描述这个岛台厨房画面中的物体、材质、颜色和风格。用中文简短回答，逗号分隔。"},
                ]
            }]
            prompt = self._processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = self._processor(
                text=prompt, images=[image], return_tensors="pt"
            ).to(self._model.device)

            out = self._model.generate(**inputs, max_new_tokens=128)
            text = self._processor.decode(out[0], skip_special_tokens=True)

            # Clean chat template artifacts (Qwen3-VL outputs user/assistant tags)
            # Extract only the assistant's response
            if "assistant" in text:
                parts = text.split("assistant")
                text = parts[-1].strip()
            # Remove any remaining user/system prompt fragments
            text = text.replace("user\n", "").replace("assistant\n", "").strip()

            # 解析标签
            res = {"caption": text, "objects": [], "materials": [], "colors": [], "style": ""}
            for p in text.replace("，", ",").split(","):
                p = p.strip()
                if not p:
                    continue
                if any(k in p for k in ["岛台", "抽屉", "烤箱", "插座", "水槽", "灯带",
                                          "冰箱", "拉篮", "餐桌", "吧台", "柜"]):
                    res["objects"].append(p)
                if any(k in p for k in ["岩板", "石", "木", "钢", "玻璃", "水泥", "不锈钢",
                                          "亚克力", "微水泥", "洞石"]):
                    res["materials"].append(p)
                if any(k in p for k in ["白", "黑", "灰", "棕", "米", "蓝", "绿", "红",
                                          "金", "银", "奶", "原木"]):
                    res["colors"].append(p)
                if any(k in p for k in ["风", "简约", "现代", "复古", "侘寂", "轻奢",
                                          "工业", "北欧", "中式", "原木"]):
                    if not res["style"]:
                        res["style"] = p

            return res
        except Exception as e:
            print(f"   [Vision] 推理失败: {e}")
            raise


# ── 线程安全单例 ──
_vision = None
_vision_lock = __import__('threading').Lock()


def get_vision_model() -> VisionModel:
    """获取全局 VisionModel 单例（线程安全）"""
    global _vision
    if _vision is None:
        with _vision_lock:
            if _vision is None:
                _vision = VisionModel()
    return _vision
