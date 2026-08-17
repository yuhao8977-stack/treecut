"""验证视觉模型是否可用 — v12.0 优化: 避免 rglob 扫描整个模型目录"""
import sys; sys.path.insert(0,".")
from pathlib import Path
print("="*50); print("  树剪 模型验证"); print("="*50)

# Check local models
models_dir = Path("models")
for m in ["Florence-2-base","Qwen3-VL-3B","Qwen3-VL-7B"]:
    p = models_dir / m
    if p.exists():
        # v12.0 修复: 仅 stat 权重文件，不执行 rglob("*") 遍历整个目录树
        sft_files = list(p.glob("*.safetensors")) + list(p.glob("*.bin"))
        size_mb = sum(f.stat().st_size for f in sft_files) / 1e6
        print(f"  {m}: {'OK' if sft_files else 'WARN'} ({size_mb:.0f}MB, {len(sft_files)} 权重文件)")
    else:
        print(f"  {m}: NOT FOUND")

# Test unified model
try:
    from core.vision_unified import VisionModel
    v = VisionModel()
    print(f"\n  当前模型: {v.model_key} -> loaded={v._loaded} available={v.available}")
    if v.available:
        print("  模型可用")
    else:
        print("  模型不可用 - 请运行 强制下载模型.bat")
except Exception as e:
    print(f"\n  模型加载失败: {e}")
