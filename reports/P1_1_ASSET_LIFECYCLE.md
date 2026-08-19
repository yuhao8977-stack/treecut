# P1.1 报告：资产生命周期 + 幂等处理 + 增量识别控制层

> 日期：2026-08-19 | 阶段：P1.1（第二阶段）
> 结论：**P1.1 READY**（全部验收通过，14/14 pytest + Test A–G + 一致性测试）

---

## 1. 目标回顾

在 P2（场景切分/ASR/OCR）大规模分析前，建立**素材处理生命周期、增量分析、防重复处理与统一资产状态系统**，确保数万视频、约 3TB 素材不会被无意义重复识别（重复烧时间/GPU/写库）。

## 2. Canonical Asset Registry 决策

审计当前库关系（v13 media_files/analysis_jobs + P1 assets + v12 库）后确认：

> **`assets` 表 = 唯一素材身份主表（Canonical Asset Registry）**

- `media_files` 是**路径视角**（source_id + relative_path 唯一）——文件移动/改名会产生新行
- `assets` 是**内容视角**（asset_id=UUID + fingerprint）——内容身份稳定
- 所有后续表（segments/ASR/OCR/labels/embedding/analysis_jobs）一律通过 `asset_id` 关联
- **禁止四套身份体系**；`asset_locations` 追踪移动/改名/多副本

详见 `docs/ASSET_DATA_MODEL.md`。

## 3. 实现内容

### 3.1 新增模块（treecut-v13 仓库）

| 模块 | 功能 |
|---|---|
| `library/processing_state.py` | 阶段状态机（9 状态 × 10 阶段）、幂等 should_process、依赖图、历史记录、Dashboard |
| `scanner/incremental.py` | 增量扫描（NEW/CHANGED/MOVED/MISSING/UNCHANGED）+ asset 协调 |
| `library/assets.py`（增强） | 内容身份协调（移动/改名/重复复用 asset_id）、asset_locations、分层哈希 needs_full_hash |
| `library/probe_worker.py`（增强） | 接入 should_process + processing_state，损坏文件对齐 SKIPPED |

### 3.2 数据表

- `asset_processing_state`：`PRIMARY KEY(asset_id, stage)`，10 阶段 × 9 状态
- `processing_history`：每次状态转移的原因（old/new/reason/model/version/time）
- `asset_locations`：位置追踪（current=1 当前路径；移动/改名/多副本）

### 3.3 状态机

```
NEW → PENDING → PROCESSING → DONE | PARTIAL | FAILED | SKIPPED | STALE | REVIEW
```

- STALE：模型/算法/文件变化后过期，需按依赖图局部重跑
- REVIEW：AI 识别待人工确认
- SKIPPED：损坏/不支持，超重试上限

### 3.4 CLI 命令

```
--inc-scan PATH            增量扫描（NEW/CHANGED/MOVED/MISSING/UNCHANGED）
--lifecycle-dashboard      各阶段全局统计
--lifecycle-list [N]       资产阶段状态列表（--stage-status/--filter-status 筛选）
--mark-stale ID STAGE REASON  手动标记 STALE（级联下游）
```

### 3.5 分层哈希（防 3TB 全量读盘）

- Fast Identity：`size + mtime + 首尾 1MiB quick hash`（扫描期）
- Full SHA256：仅 `needs_full_hash()` 判定为疑似重复（同 quick 多 asset）或 ≥200MB 大文件才计算
- 实测：5 文件扫描 0.03s，未触发 full hash（无重复疑点）

## 4. 测试结果（真实执行）

### 4.1 pytest：14/14 通过

```
tests/test_p11_lifecycle.py   8 passed  ← P1.1 核心
tests/test_p1_assets.py       4 passed  ← P1 回归
tests/test_p1_migrate.py      2 passed  ← P1 回归
```

### 4.2 Test A–G（真实临时库 + 真实视频）

| 测试 | 场景 | 结果 |
|---|---|---|
| A | 首次扫描全部建库 | ✅ 5 文件 → 4 canonical asset（1 对重复合并），10 阶段状态行 |
| B | 二次扫描不重复处理 | ✅ new:0, unchanged:5；should_process 返回 SKIP_ALREADY_DONE |
| C | 改名 | ✅ asset_id 不变，当前位置更新 renamed.mp4，probe 状态保留 |
| D | 移动目录 | ✅ asset_id 不变，同 fingerprint 仅 1 个 asset |
| E | 修改文件 | ✅ probe/scene → STALE（INPUT_CHANGED 级联） |
| F | ASR 模型升级 | ✅ 仅 asr/labels/embedding STALE；scene/keyframe/ocr/duplicate 保持 DONE |
| G | 强制中断恢复 | ✅ PROCESSING → PENDING（recover） |

### 4.3 一致性测试

- 同 fingerprint 只允许一个 canonical asset ✅（5 文件 → 4 身份）
- asset_id + stage 唯一约束 ✅
- 重复文件（clip_a + clip_a_duplicate）合并为同一 asset，asset_locations 记录 2 位置 ✅

### 4.4 CLI 端到端

```
inc-scan（首次）: total 5, new 5
inc-scan（二次）: total 5, new 0, unchanged 5   ← 不重复
probe-assets:    3 DONE + 1 SKIPPED（损坏 broken.mp4）
lifecycle-dashboard: probe DONE:3 SKIPPED:1
改名 clip_a:     assets total 仍 4（复用，未新增）  ← 改名不产生新 asset
```

## 5. 哈希 Benchmark（P1.1 §八）

| 集合 | 扫描耗时 | full hash 触发 |
|---|---|---|
| 5 文件（合成） | 0.03–0.04s | 0（无重复疑点） |
| 真实输出目录 18 文件 | 0.46s（catalog.scan 原生） | 按需 |

> 说明：Z 网络盘（\\X1）当前间歇不可访问，100/1000 真实视频 Benchmark 待 Z 盘可用后执行（增量扫描已就绪，届时直接 `--inc-scan <Z盘小目录>`）。

## 6. 未解决问题 / 遗留

1. **Z 盘全量扫描**：待 Z 盘可用，按 10–50GB 小目录起步（`--inc-scan` 已支持）
2. **UI 状态显示**：P1.1 提供 CLI 状态（dashboard/list/filter）；完整 UI 9 页在 BACKLOG.md 规划（P 阶段推进时实现）
3. **素材根目录配置**：v13 `Settings.material_sources` 已存在（绝对路径校验），CLI 当前用 `--inc-scan PATH` 显式传参；UI 层接 settings.json
4. **并行 worker（2–6 路）**：P1.1 未做并发，防机械盘 IO 打满（P1.1 后续增强或 P2 接入）
5. **完整 SHA256 后台补算**：`--probe-assets` 后可用 `finalize_fingerprint(force=True)` 对疑似重复后台补 full hash

## 7. Git 提交

- 仓库：`yuhao8977-stack/treecut-v13`（公开）
- 新增：`library/processing_state.py`、`scanner/`、`docs/ASSET_DATA_MODEL.md`、`docs/PIPELINE_DEPENDENCIES.md`、`tests/test_p11_lifecycle.py`、`BACKLOG.md`
- 增强：`library/assets.py`（内容协调/分层哈希/位置）、`library/probe_worker.py`（生命周期接入）、`main.py`（P1.1 CLI）
- 未上传：视频/模型/运行库/密钥（.gitignore 已覆盖）

---

## 8. 结论

**P1.1 READY**

系统现在明确知道每个素材每个阶段的处理状态，能：
- 第二次扫描不重复处理（UNCHANGED 跳过）
- 移动/改名不产生新 asset（asset_id 复用）
- 文件修改正确触发下游 STALE
- 模型升级只局部重跑（依赖图）
- 中断自动恢复（断点续跑）
- 分层哈希避免 3TB 全量读盘

**按停止条件，P1.1 完成立即停止，未进入 P2。** 等待用户「继续第二阶段P2」。
