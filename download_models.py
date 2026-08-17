#!/usr/bin/env python3
"""
树剪 — 视觉模型下载工具
支持: Qwen3-VL / Kimi-VL / Tarsier2 / Florence-2 / Qwen2.5-VL (Ollama)
用法: python download_models.py                    (交互选择)
      python download_models.py --model qwen3-7b   (指定模型)
      python download_models.py --list              (列出可用)
"""
import sys, os, subprocess, argparse
from pathlib import Path

MODELS = {
    "qwen3-7b": {
        "name": "Qwen3-VL-7B",
        "hf": "Qwen/Qwen3-VL-7B",
        "size": "~14GB",
        "type": "transformers",
        "desc": "阿里通义最新视觉大模型, 推荐首选"
    },
    "qwen3-3b": {
        "name": "Qwen3-VL-3B",
        "hf": "Qwen/Qwen3-VL-3B",
        "size": "~6GB",
        "type": "transformers",
        "desc": "Qwen3-VL轻量版, 显存不足时推荐"
    },
    "kimi-vl": {
        "name": "Kimi-VL-A3B-Instruct",
        "hf": "moonshotai/Kimi-VL-A3B-Instruct",
        "size": "~6GB",
        "type": "transformers",
        "desc": "月之暗面轻量视觉模型"
    },
    "tarsier2": {
        "name": "Tarsier2-7B",
        "hf": "Tarsier2-7B",
        "size": "~14GB",
        "type": "transformers",
        "desc": "字节跳动视频理解专用模型"
    },
    "florence2": {
        "name": "Florence-2-base",
        "hf": "microsoft/Florence-2-base",
        "size": "~0.5GB",
        "type": "transformers",
        "desc": "微软轻量视觉模型, 兜底选择"
    },
    "qwen2.5-ollama": {
        "name": "Qwen2.5-VL:7B (Ollama)",
        "cmd": "ollama pull qwen2.5vl:7b",
        "size": "~5GB",
        "type": "ollama",
        "desc": "当前默认模型, 通过Ollama运行"
    },
}


def list_models():
    print("\n可用视觉模型:\n")
    for key, m in MODELS.items():
        print(f"  {key:18s} {m['name']:30s} {m['size']:>8s}  {m['desc']}")
    print()


def download_transformers(model_key):
    m = MODELS[model_key]
    print(f"\n📥 正在下载 {m['name']} ({m['size']})...")
    print(f"   HuggingFace: {m['hf']}")
    print(f"   模型将缓存到: {os.path.expanduser('~/.cache/huggingface/hub/')}")
    print(f"   ⏳ 首次下载需较长时间, 请耐心等待...\n")

    try:
        from huggingface_hub import snapshot_download
        snapshot_download(m["hf"], resume_download=True, max_workers=4)
        print(f"   ✅ {m['name']} 下载完成!")
        return True
    except ImportError:
        print("   ❌ 需要安装 huggingface_hub: pip install huggingface_hub")
        print(f"   或手动下载: https://huggingface.co/{m['hf']}")
        return False
    except Exception as e:
        print(f"   ❌ 下载失败: {e}")
        return False


def download_ollama(model_key):
    m = MODELS[model_key]
    print(f"\n📥 正在通过Ollama下载 {m['name']}...")
    try:
        subprocess.run(m["cmd"].split(), check=True)
        print(f"   ✅ {m['name']} 下载完成!")
        return True
    except Exception as e:
        print(f"   ❌ 下载失败: {e}")
        return False


def install_dependencies():
    """安装必要的依赖"""
    print("\n📦 检查依赖...")
    deps = ["transformers>=4.45.0", "huggingface_hub", "accelerate", "torch", "Pillow"]
    for dep in deps:
        try:
            pkg = dep.split(">=")[0].split("==")[0]
            __import__(pkg.replace("-", "_"))
            print(f"   ✅ {dep}")
        except ImportError:
            print(f"   📥 安装 {dep}...")
            subprocess.run([sys.executable, "-m", "pip", "install", dep, "-q"])
    print("   ✅ 依赖就绪\n")


def main():
    p = argparse.ArgumentParser(description="树剪 视觉模型下载工具")
    p.add_argument("--model", "-m", type=str, help="指定模型key (如 qwen3-7b, kimi-vl)")
    p.add_argument("--list", "-l", action="store_true", help="列出可用模型")
    p.add_argument("--install-deps", action="store_true", help="安装依赖")
    args = p.parse_args()

    if args.install_deps:
        install_dependencies()

    if args.list:
        list_models()
        return

    if args.model:
        key = args.model
        if key not in MODELS:
            print(f"未知模型: {key}"); list_models(); return
        install_dependencies()
        m = MODELS[key]
        if m["type"] == "transformers":
            download_transformers(key)
        elif m["type"] == "ollama":
            download_ollama(key)
        return

    # 交互模式
    list_models()
    print("推荐方案:")
    print("  1. 首选: qwen3-7b (功能最强)")
    print("  2. 轻量: florence2 (仅0.5GB, 快速可用)")
    print("  3. 保持: qwen2.5-ollama (当前默认)")
    try:
        choice = input("\n请选择模型key (如 qwen3-7b): ").strip()
        if choice in MODELS:
            install_dependencies()
            m = MODELS[choice]
            if m["type"] == "transformers":
                download_transformers(choice)
            elif m["type"] == "ollama":
                download_ollama(choice)
        else:
            print("无效选择")
    except (EOFError, KeyboardInterrupt):
        print("\n已取消")


if __name__ == "__main__":
    main()
