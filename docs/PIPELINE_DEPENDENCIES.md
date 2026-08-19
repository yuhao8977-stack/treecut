# PIPELINE_DEPENDENCIES.md — 处理阶段依赖图（Stage Dependency Graph）

> 日期：2026-08-19 | 阶段：P1.1

---

## 1. 依赖图

```
probe（ffprobe 元数据）
  │
fingerprint（指纹）
  │
duplicate（重复识别）── 依赖 fingerprint
  │
scene（场景切分）── 依赖 probe + fingerprint
  │
keyframe（关键帧）── 依赖 probe + scene
  ├── ocr（字幕/文字）── 依赖 keyframe
  ├── vision（视觉理解）── 依赖 keyframe
  │
asr（语音转写）── 依赖 probe + fingerprint
  │
labels（运营标签）── 依赖 asr + ocr + vision
  │
embedding（向量嵌入）── 依赖 keyframe + labels
```

### 具体依赖（stage → 上游完成才可处理）

| Stage | 依赖的上游 |
|---|---|
| probe | — |
| fingerprint | probe |
| duplicate | fingerprint |
| scene | probe, fingerprint |
| keyframe | probe, scene |
| asr | probe, fingerprint |
| ocr | keyframe |
| vision | keyframe |
| labels | asr, ocr, vision |
| embedding | keyframe, labels |

---

## 2. 失效传播（谁 STALE 会波及谁）

实现于 `processing_state.invalidated_by(stage)`（传递闭包）：

| 上游变化 | 级联 STALE 的下游 |
|---|---|
| probe | probe, fingerprint, duplicate, scene, keyframe, asr, ocr, vision, labels, embedding |
| fingerprint | fingerprint, duplicate, scene, keyframe, asr, ocr, vision, labels, embedding |
| duplicate | duplicate |
| scene | scene, keyframe, ocr, vision, labels, embedding |
| keyframe | keyframe, ocr, vision, labels, embedding |
| asr | asr, labels, embedding |
| ocr | ocr, labels, embedding |
| vision | vision, labels, embedding |
| labels | labels, embedding |
| embedding | embedding |

### 示例：ASR 模型升级（faster-whisper small → medium）

```text
仅 asr → STALE（因 model_version 变化）
级联：labels → STALE（依赖 asr），embedding → STALE（依赖 labels）
保持 DONE：scene / keyframe / ocr / duplicate / probe / fingerprint
```

→ **只重跑 ASR，不无理由重跑 scene/keyframe/ocr/embedding 等无关阶段。**

### 示例：文件内容变化（fingerprint 变）

```text
probe → STALE（INPUT_CHANGED）
级联：全部下游 → STALE
→ 重新进入处理队列，按依赖顺序重跑
```

---

## 3. 幂等判定（should_process）

每次 worker 处理前调用（P1.1 §四）：

```python
decision = ps.should_process(
    asset_id, stage,
    pipeline_version="P1.1",
    algorithm_version="...",
    model_name="faster-whisper", model_version="small",
    input_fingerprint=quick_fingerprint,
)
# 返回:
#   SKIP_ALREADY_DONE — fingerprint+pipeline+model 一致且 DONE，绝不重跑
#   NEED_REPROCESS    — 版本/指纹变化或状态非 DONE
```

判定顺序：无状态 → 非 DONE → fingerprint 不同 → pipeline 不同 →
algorithm 不同 → model 不同 → model_version 不同 → SKIP。

---

## 4. Worker 统一入口（P2+ 强制）

所有分析 worker（scene/keyframe/asr/ocr/vision/labels/embedding）必须：

```text
should_process()
  → claim（事务置 PROCESSING）
  → run（真实处理）
  → save（结果落库）
  → DONE / FAILED / SKIPPED / REVIEW
```

禁止绕过生命周期系统直接写结果。
