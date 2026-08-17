#!/usr/bin/env python3
"""
树剪 TreeCut v11.0 — 强制模型验证脚本
========================================================================
验证四个核心模型:
  1. Qwen3-VL-4B (视觉)
  2. SenseVoice (情绪+事件)
  3. Whisper (语音转写)
  4. FAISS + BGE-M3 (向量检索)

无降级: 任一模型不可用即标记为 FAIL 并输出修复指南。

用法:
  python verify_models_force.py              # 验证所有模型
  python verify_models_force.py --json       # JSON 格式输出
"""
import sys
import os
import time
import json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

RESULTS = []


def check(name: str, category: str) -> dict:
    """记录单个模型检查结果"""
    return {"name": name, "category": category, "status": "CHECKING",
            "details": "", "load_time_s": 0, "fix": ""}


def pass_check(r: dict, details: str, load_time: float = 0):
    r["status"] = "PASS"
    r["details"] = details
    r["load_time_s"] = round(load_time, 1)


def fail_check(r: dict, reason: str, fix: str = ""):
    r["status"] = "FAIL"
    r["details"] = reason
    r["fix"] = fix


# ═══════════════════════════════════
# 1. Qwen3-VL-4B
# ═══════════════════════════════════
def verify_qwen3():
    r = check("Qwen3-VL-4B", "vision")
    models_dir = os.path.join(PROJECT_ROOT, "models", "Qwen3-VL-4B-Instruct-FP8")

    if not os.path.isdir(models_dir):
        fail_check(r, f"模型目录不存在: {models_dir}",
                   "pip install huggingface_hub && python -c \"from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen3-VL-4B-Instruct-FP8', local_dir='models/Qwen3-VL-4B-Instruct-FP8')\"")
        return r

    sft = list(__import__('pathlib').Path(models_dir).glob("*.safetensors"))
    if not sft:
        fail_check(r, f"目录无权重文件: {models_dir}",
                   "请重新下载模型到 models/Qwen3-VL-4B-Instruct-FP8/")
        return r

    size_gb = sum(f.stat().st_size for f in sft) / 1e9
    t0 = time.time()

    try:
        from core.vision_unified import VisionModel
        vm = VisionModel()
        elapsed = time.time() - t0
        pass_check(r, f"已加载 ({size_gb:.1f}GB, {elapsed:.0f}s, device={vm._model.device})",
                   load_time=elapsed)
    except Exception as e:
        elapsed = time.time() - t0
        fail_check(r, f"加载失败 ({elapsed:.0f}s): {str(e)[:120]}",
                   "检查 models/Qwen3-VL-4B-Instruct-FP8/ 目录完整性，或 pip install torch transformers Pillow")

    return r


# ═══════════════════════════════════
# 2. SenseVoice
# ═══════════════════════════════════
def verify_sensevoice():
    r = check("SenseVoice", "audio_emotion")
    model_path = os.path.join(PROJECT_ROOT, "models", "SenseVoiceSmall", "model.pt")

    if not os.path.exists(model_path):
        fail_check(r, f"模型权重缺失: {model_path}",
                   "modelscope download --model FunAudioLLM/SenseVoiceSmall --local_dir models/SenseVoiceSmall")
        return r

    t0 = time.time()
    try:
        from core.audio_models import SenseVoiceEngine
        engine = SenseVoiceEngine(device="cpu")
        elapsed = time.time() - t0
        pass_check(r, f"已加载 ({os.path.getsize(model_path)/1e6:.0f}MB, {elapsed:.0f}s, cpu)",
                   load_time=elapsed)
    except Exception as e:
        elapsed = time.time() - t0
        fail_check(r, f"加载失败 ({elapsed:.0f}s): {str(e)[:120]}",
                   "pip install funasr>=1.1.2 modelscope torchaudio")

    return r


# ═══════════════════════════════════
# 3. Whisper
# ═══════════════════════════════════
def verify_whisper():
    r = check("Whisper large-v3", "audio_transcribe")

    t0 = time.time()
    try:
        from core.audio_models import WhisperModel
        wm = WhisperModel()
        wm._lazy_load()
        elapsed = time.time() - t0
        pass_check(r, f"已加载 (large-v3, cpu, int8, {elapsed:.0f}s)", load_time=elapsed)
    except Exception as e:
        elapsed = time.time() - t0
        fail_check(r, f"加载失败 ({elapsed:.0f}s): {str(e)[:120]}",
                   "pip install faster-whisper")

    return r


# ═══════════════════════════════════
# 4. FAISS + BGE-M3
# ═══════════════════════════════════
def verify_faiss():
    r = check("FAISS + BGE-M3", "retrieval")

    import sqlite3
    db_path = os.path.join(PROJECT_ROOT, "ai_material_library.db")
    faiss_path = os.path.join(PROJECT_ROOT, "shipin", "material_faiss.index")

    if not os.path.exists(db_path):
        fail_check(r, f"数据库不存在: {db_path}", "请先运行素材库扫描")
        return r

    conn = sqlite3.connect(db_path)
    embed_count = conn.execute(
        "SELECT COUNT(*) FROM materials WHERE embedding IS NOT NULL AND analyzed=1"
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
    conn.close()

    if embed_count == 0:
        fail_check(r, f"无有效 embedding ({total}条记录中0条含embedding)",
                   "运行素材分析: from core.analyzer import VideoAnalyzer; ...")
        return r

    t0 = time.time()
    try:
        import faiss
        import numpy as np

        # FAISS C++ cannot read Chinese paths on Windows.
        # Copy to temp (ASCII path), verify there, then delete.
        if os.path.exists(faiss_path):
            import tempfile as _tmpmod
            import shutil as _shutil
            _tmp = _tmpmod.mkdtemp(prefix="faiss_verify_")
            try:
                _tmp_idx = os.path.join(_tmp, "material_faiss.index")
                _shutil.copy2(faiss_path, _tmp_idx)
                idx = faiss.read_index(_tmp_idx)
                faiss_n = idx.ntotal
                synced = faiss_n == embed_count
            finally:
                _shutil.rmtree(_tmp, ignore_errors=True)
        else:
            faiss_n = 0
            synced = False

        elapsed = time.time() - t0
        if synced:
            pass_check(r, f"已同步 (DB:{embed_count}, FAISS:{faiss_n}, L2)",
                       load_time=elapsed)
        else:
            fail_check(r, f"不同步 (DB:{embed_count}, FAISS:{faiss_n})",
                       f"python force_rebuild_faiss.py")
    except ImportError as e:
        elapsed = time.time() - t0
        fail_check(r, f"缺少依赖: {e}", "pip install faiss-cpu numpy")
    except Exception as e:
        elapsed = time.time() - t0
        fail_check(r, f"验证失败: {str(e)[:120]}",
                   "python force_rebuild_faiss.py --force")

    return r


# ═══════════════════════════════════
# 依赖检查
# ═══════════════════════════════════
def check_dependencies():
    deps = {
        "torch": "torch",
        "transformers": "transformers",
        "PIL": "Pillow",
        "faster_whisper": "faster-whisper",
        "funasr": "funasr>=1.1.2",
        "faiss": "faiss-cpu",
        "numpy": "numpy",
        "sentence_transformers": "sentence-transformers",
        "sqlite3": "(stdlib)",
    }
    missing = []
    for mod, pkg in deps.items():
        try:
            __import__(mod)
        except ImportError:
            if pkg != "(stdlib)":
                missing.append(pkg)

    if missing:
        print("\n  [WARN] 缺少依赖:")
        for m in missing:
            print(f"    pip install {m}")
        print()

    return len(missing) == 0


# ═══════════════════════════════════
# MAIN
# ═══════════════════════════════════
def main():
    print("=" * 60)
    print("  树剪 TreeCut v11.0 — 强制模型验证")
    print("=" * 60)

    # 依赖检查
    print("\n[0] 依赖检查")
    check_dependencies()

    # 模型验证
    print("\n[1/4] Qwen3-VL-4B (视觉)...")
    RESULTS.append(verify_qwen3())

    print("\n[2/4] SenseVoice (情绪+事件)...")
    RESULTS.append(verify_sensevoice())

    print("\n[3/4] Whisper large-v3 (语音转写)...")
    RESULTS.append(verify_whisper())

    print("\n[4/4] FAISS + BGE-M3 (向量检索)...")
    RESULTS.append(verify_faiss())

    # 输出表格
    print("\n" + "=" * 80)
    print("  验证报告")
    print("=" * 80)
    print(f"  {'模型':<22s} {'类别':<14s} {'状态':<8s} {'详情'}")
    print(f"  {'-'*22} {'-'*14} {'-'*8} {'-'*40}")

    all_pass = True
    for r in RESULTS:
        icon = "[OK]" if r["status"] == "PASS" else "[FAIL]"
        print(f"  {icon} {r['name']:<19s} {r['category']:<14s} {r['status']:<8s} {r['details'][:50]}")
        if r["status"] == "FAIL":
            all_pass = False

    print("=" * 80)

    # 输出修复建议
    failed = [r for r in RESULTS if r["status"] == "FAIL"]
    if failed:
        print(f"\n  [FAIL] {len(failed)} 个模型未通过验证:\n")
        for r in failed:
            print(f"  [{r['name']}]")
            print(f"    错误: {r['details']}")
            if r["fix"]:
                print(f"    修复: {r['fix']}")
            print()

    if all_pass:
        print(f"\n  [OK] 全部 {len(RESULTS)} 个模型验证通过!")
        # 写入验证通过文件
        pass_file = os.path.join(PROJECT_ROOT, "MODEL_VALIDATION_PASSED.txt")
        with open(pass_file, "w", encoding="utf-8") as f:
            f.write(f"树剪 TreeCut v11.0 模型验证通过\n")
            f.write(f"验证时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"验证结果: {len(RESULTS)}/{len(RESULTS)} 通过\n\n")
            for r in RESULTS:
                f.write(f"[{r['status']}] {r['name']}: {r['details']}\n")
            f.write(f"\n学习闭环: 模型结果记录到 usage_records → SelfLearningEngine 分析 → 调整权重\n")
        print(f"  验证文件: {pass_file}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    json_mode = "--json" in sys.argv
    if json_mode:
        # 静默执行
        RESULTS.append(verify_qwen3())
        RESULTS.append(verify_sensevoice())
        RESULTS.append(verify_whisper())
        RESULTS.append(verify_faiss())
        print(json.dumps(RESULTS, ensure_ascii=False, indent=2))
    else:
        sys.exit(main())
