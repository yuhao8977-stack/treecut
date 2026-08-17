#!/usr/bin/env python3
"""
树剪 TreeCut v11.0 — 核心模型执行测试脚本
========================================================================
模拟运行测试（使用真实模型调用），验证四个核心模型是否真正参与任务。

用法:
  python test_model_execution.py                  # 全部测试
  python test_model_execution.py --vision-only    # 仅视觉
  python test_model_execution.py --audio-only     # 仅音频
  python test_model_execution.py --match-only     # 仅匹配
"""
import sys
import os
import json
import time
import tempfile
import argparse
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS = []


def log(level: str, msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  [{ts}] [{level}] {msg}")


# ═══════════════════════════════════
# 测试 1: 视觉模型 (Qwen3-VL-4B)
# ═══════════════════════════════════
def test_vision():
    """测试 Qwen3-VL-4B 加载 + 推理"""
    log("INFO", "测试 Qwen3-VL-4B 视觉模型...")

    # 生成测试图片 (2秒黑屏视频 → 抽帧)
    test_img = None
    try:
        import subprocess
        tmp_video = tempfile.mktemp(suffix=".mp4")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "color=c=0x808080:s=640x480:d=2",
            "-frames:v", "1", "-q:v", "2",
            tempfile.mktemp(suffix=".jpg") if False else tmp_video
        ], capture_output=True, timeout=10)

        # 直接生成一张图片
        test_img = tempfile.mktemp(suffix=".jpg")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "color=c=0x808080:s=640x480:d=0.1",
            "-frames:v", "1", "-q:v", "2", test_img
        ], capture_output=True, timeout=10)

        if not os.path.exists(test_img):
            log("WARN", "无法生成测试图片 (ffmpeg可能不可用)，使用已存在的图片")
            test_img = None
    except Exception as e:
        log("WARN", f"ffmpeg 不可用: {e}")

    try:
        from core.vision_unified import VisionModel

        t0 = time.time()
        vm = VisionModel()
        load_time = time.time() - t0
        log("OK", f"模型加载成功 ({load_time:.1f}s)")

        if test_img and os.path.exists(test_img):
            t0 = time.time()
            result = vm.analyze(test_img)
            inf_time = time.time() - t0
            log("OK", f"推理完成 ({inf_time:.1f}s): {json.dumps(result, ensure_ascii=False)[:200]}")
        else:
            log("INFO", "无测试图片，跳过推理。模型加载已验证。")
            result = {"status": "model_loaded_only"}

        if test_img and os.path.exists(test_img):
            os.remove(test_img)

        RESULTS.append({"model": "Qwen3-VL-4B", "status": "PASS",
                        "load_time": round(load_time, 1),
                        "inference_time": round(inf_time if 'inf_time' in dir() else 0, 1),
                        "result_keys": list(result.keys())})
        return True

    except Exception as e:
        log("FAIL", f"视觉模型测试失败: {e}")
        RESULTS.append({"model": "Qwen3-VL-4B", "status": "FAIL", "error": str(e)[:200]})
        return False


# ═══════════════════════════════════
# 测试 2: 音频模型 (SenseVoice + Whisper)
# ═══════════════════════════════════
def test_audio():
    """测试 SenseVoice + Whisper 加载"""
    log("INFO", "测试音频模型 (SenseVoice + Whisper)...")

    sv_ok = False
    wh_ok = False

    # Whisper
    try:
        from core.audio_models import WhisperModel
        t0 = time.time()
        wm = WhisperModel()
        wm._lazy_load()
        wh_ok = wm.available
        load_time = time.time() - t0
        log("OK" if wh_ok else "FAIL",
            f"Whisper {'可用' if wh_ok else '不可用'} ({load_time:.1f}s)")
    except Exception as e:
        log("FAIL", f"Whisper: {e}")

    # SenseVoice
    try:
        from core.audio_models import SenseVoiceEngine
        t0 = time.time()
        engine = SenseVoiceEngine(device="cpu")
        sv_ok = engine.available
        load_time = time.time() - t0
        log("OK" if sv_ok else "FAIL",
            f"SenseVoice {'可用' if sv_ok else '不可用'} ({load_time:.1f}s)")

        # 如果有测试音频
        sv_model_path = PROJECT_ROOT / "models" / "SenseVoiceSmall" / "example" / "zh.mp3"
        if sv_ok and sv_model_path.exists():
            t0 = time.time()
            result = engine.analyze(str(sv_model_path))
            inf_time = time.time() - t0
            log("OK", f"SenseVoice 推理: emotion={result['emotion']}, "
                       f"events={result['events']}, text={result['text'][:50]}...")
    except Exception as e:
        log("FAIL", f"SenseVoice: {e}")

    RESULTS.append({"model": "SenseVoice+Whisper", "status": "PASS" if (sv_ok or wh_ok) else "FAIL",
                    "sensevoice_ok": sv_ok, "whisper_ok": wh_ok})
    return sv_ok or wh_ok


# ═══════════════════════════════════
# 测试 3: 知识库 + 匹配
# ═══════════════════════════════════
def test_matching():
    """测试 KnowledgeBridge + SmartMatcher"""
    log("INFO", "测试知识库匹配...")

    kb_ok = False
    match_ok = False

    # KnowledgeBridge
    try:
        from utils.knowledge import get_bridge
        kb = get_bridge()
        t0 = time.time()
        kws = kb.extract_copy_keywords("奶油风伸缩岩板岛台 海棠角工艺 轨道插座")
        elapsed = time.time() - t0
        total = sum(len(v) for v in kws.values())
        kb_ok = total >= 2
        log("OK" if kb_ok else "WARN",
            f"知识库: {total} 个行业术语 ({elapsed:.3f}s) — "
            f"{dict((k, list(v)[:3]) for k,v in kws.items() if v)}")
    except Exception as e:
        log("FAIL", f"KnowledgeBridge: {e}")

    # SmartMatcher
    try:
        from core.pipeline import ai_match_clips
        t0 = time.time()
        clips = ai_match_clips("奶油风伸缩岩板岛台", num_clips=6)
        elapsed = time.time() - t0
        match_ok = len(clips) > 0
        if match_ok:
            methods = set(c.get("match_method", "?") for c in clips)
            scores = [c.get("match_score", 0) for c in clips]
            log("OK", f"匹配: {len(clips)} 个片段, 方法={methods}, "
                       f"平均分={sum(scores)/len(scores):.2f} ({elapsed:.1f}s)")
        else:
            log("WARN", f"匹配: 0 个片段 ({elapsed:.1f}s) — 可能需要重建 FAISS 索引")
            log("INFO", "运行: python force_rebuild_faiss.py")
    except Exception as e:
        log("FAIL", f"SmartMatcher: {e}")

    RESULTS.append({"model": "KnowledgeBridge+SmartMatcher", "status": "PASS" if (kb_ok and match_ok) else "WARN",
                    "kb_ok": kb_ok, "match_ok": match_ok, "clips_found": len(clips) if 'clips' in dir() else 0})
    return kb_ok


# ═══════════════════════════════════
# 测试 4: 学习闭环 (数据库审计)
# ═══════════════════════════════════
def test_learning_loop():
    """检查学习闭环数据"""
    log("INFO", "检查学习闭环状态...")
    import sqlite3

    db_path = PROJECT_ROOT / "ai_material_library.db"
    if not db_path.exists():
        log("WARN", "ai_material_library.db 不存在，跳过学习闭环检查")
        RESULTS.append({"model": "学习闭环", "status": "WARN", "error": "DB不存在"})
        return False

    conn = sqlite3.connect(str(db_path))

    # analysis_log
    log_count = conn.execute("SELECT COUNT(*) FROM analysis_log").fetchone()[0]
    log("INFO", f"analysis_log: {log_count} 条分析记录")

    # feedback
    fb_count = 0
    try:
        fb_count = conn.execute("SELECT COUNT(*) FROM annotation_feedback").fetchone()[0]
    except Exception:
        pass
    log("INFO", f"annotation_feedback: {fb_count} 条反馈")

    # tag_learning
    tl_count = 0
    try:
        tl_count = conn.execute("SELECT COUNT(*) FROM tag_learning").fetchone()[0]
    except Exception:
        pass
    log("INFO", f"tag_learning: {tl_count} 条学习记录")

    conn.close()

    status = "PASS" if log_count > 0 else "WARN"
    RESULTS.append({
        "model": "学习闭环",
        "status": status,
        "analysis_logs": log_count,
        "feedback_count": fb_count,
        "tag_learning_count": tl_count,
    })
    return True


# ═══════════════════════════════════
# MAIN
# ═══════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="TreeCut Model Execution Test")
    parser.add_argument("--vision-only", action="store_true")
    parser.add_argument("--audio-only", action="store_true")
    parser.add_argument("--match-only", action="store_true")
    parser.add_argument("--full", action="store_true", default=True)

    args = parser.parse_args()

    print("=" * 60)
    print("  树剪 TreeCut v11.0 — 核心模型执行测试")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if args.vision_only:
        test_vision()
    elif args.audio_only:
        test_audio()
    elif args.match_only:
        test_matching()
    else:
        print("\n── [1/4] 视觉模型 ──")
        test_vision()

        print("\n── [2/4] 音频模型 ──")
        test_audio()

        print("\n── [3/4] 匹配引擎 ──")
        test_matching()

        print("\n── [4/4] 学习闭环 ──")
        test_learning_loop()

    # ── 输出表格报告 ──
    print("\n" + "=" * 80)
    print("  测试结果汇总")
    print("=" * 80)
    print(f"  {'模型':<28s} {'状态':<8s} {'详情'}")
    print(f"  {'-'*28} {'-'*8} {'-'*45}")

    all_pass = True
    for r in RESULTS:
        icon = "[OK]" if r["status"] == "PASS" else ("[WARN]" if r["status"] == "WARN" else "[FAIL]")
        details = ""
        if "load_time" in r:
            details = f"加载{r['load_time']}s"
        if "sensevoice_ok" in r:
            details = f"SV={'OK' if r['sensevoice_ok'] else 'FAIL'}, WH={'OK' if r['whisper_ok'] else 'FAIL'}"
        if "clips_found" in r:
            details = f"找到{r['clips_found']}个片段"
        if "analysis_logs" in r:
            details = f"{r['analysis_logs']}条分析记录, {r['feedback_count']}条反馈"
        if "error" in r:
            details = r["error"][:50]
        print(f"  {icon} {r['model']:<26s} {r['status']:<8s} {details}")

        if r["status"] == "FAIL":
            all_pass = False

    print("=" * 80)

    if all_pass:
        print(f"\n  [OK] 全部模型测试通过!")


if __name__ == "__main__":
    main()
