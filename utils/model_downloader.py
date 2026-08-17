"""模型下载器 — download_model + ensure_model_available"""
import os, sys, subprocess
from pathlib import Path

MODEL_HF = {"qwen3-7b":"Qwen/Qwen3-VL-7B","qwen3-3b":"Qwen/Qwen3-VL-3B","kimi-vl":"moonshotai/Kimi-VL-A3B-Instruct","tarsier2":"Tarsier2-7B","florence2":"microsoft/Florence-2-base"}
MODEL_SIZE = {"qwen3-7b":"14GB","qwen3-3b":"6GB","kimi-vl":"6GB","tarsier2":"14GB","florence2":"0.5GB"}

def ensure_model_available(model_key="qwen2.5-ollama") -> bool:
    """确保模型可用 — ollama直接检测, transformers检查缓存"""
    if model_key == "qwen2.5-ollama" or "ollama" in model_key:
        try:
            import urllib.request, json
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                r = json.loads(resp.read())
            installed = [m["name"] for m in r.get("models",[])]
            return any("qwen2.5vl" in m or "qwen3-vl" in m for m in installed)
        except Exception: return False
    hf_name = MODEL_HF.get(model_key,"")
    if not hf_name: return False
    cache = Path.home()/".cache"/"huggingface"/"hub"/f"models--{hf_name.replace('/','--')}"
    return cache.exists()

def download_model(model_key, progress_callback=None):
    """下载指定模型到本地缓存, 带进度"""
    if model_key == "qwen2.5-ollama":
        print(f"📥 下载Qwen2.5-VL via Ollama...")
        return subprocess.run(["ollama","pull","qwen2.5vl:7b"]).returncode == 0
    hf_name = MODEL_HF.get(model_key,"")
    if not hf_name: return False
    print(f"📥 下载 {model_key} ({MODEL_SIZE.get(model_key,'?')}): {hf_name}")
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(hf_name, resume_download=True, max_workers=4)
        return True
    except ImportError:
        print("请先: pip install huggingface_hub"); return False
    except Exception as e: print(f"失败: {e}"); return False

def list_available():
    """列出可用模型状态"""
    print("\n模型状态:")
    for k in MODEL_HF: print(f"  {k:12s} {MODEL_SIZE[k]:>6s} {'✅已缓存' if ensure_model_available(k) else '❌需下载'}")
    print(f"  {'qwen2.5-ollama':12s} {'5GB':>6s} {'✅可用' if ensure_model_available('qwen2.5-ollama') else '❌未安装'}")
