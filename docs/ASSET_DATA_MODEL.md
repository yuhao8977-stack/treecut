# ASSET_DATA_MODEL.md — 树剪统一资产数据模型（Canonical Asset Registry）

> 日期：2026-08-19 | 阶段：P1.1 | 依据：真实代码审计（v13 Catalog + P1 Assets）

---

## 1. 结论：Canonical Asset Registry = `assets` 表

审计现有关系后确认：**`assets` 是唯一素材身份主表（Canonical Asset Registry）**。

```
FILE（文件系统）
  ↓ 扫描登记（catalog.scan）
media_files（路径视角：source_id + relative_path 唯一）
  ↓ 内容身份协调（P1.1）
assets（内容视角：asset_id 稳定 = UUID + fingerprint）  ★ CANONICAL
  ├── asset_processing_state（阶段级处理状态）
  ├── processing_history（状态转移历史）
  ├── asset_locations（位置追踪：移动/改名/重复副本）
  ├── media_tags（标签）
  └── analysis_jobs（v13 分析任务）
```

**身份规则**：
- `asset_id` = UUID（稳定身份，跨路径/改名/移动不变）
- 内容身份 = `fingerprint_quick`（size + 首尾 1MiB SHA256）+ `fingerprint_full`（完整 SHA256，仅疑似重复时计算）
- 同一内容（quick fingerprint 相同）**只允许一个 canonical asset**——移动/改名/重复副本全部复用，禁止创建第二个身份

**禁止四套身份体系**：GUI / workflow / analysis / search 全部通过 `asset_id` 关联，各自不得重新创建"视频身份"。

---

## 2. 表结构

### assets（Canonical Asset Registry）

```sql
CREATE TABLE assets (
    asset_id TEXT PRIMARY KEY,            -- UUID（稳定身份）
    media_id INTEGER REFERENCES media_files(id) ON DELETE CASCADE,  -- 首次关联
    fingerprint_quick TEXT NOT NULL,      -- size+首尾1MiB（快速身份）
    fingerprint_full TEXT NOT NULL,       -- 完整SHA256（疑似重复才计算）
    file_size INTEGER NOT NULL,
    duration REAL, width INTEGER, height INTEGER, fps REAL,
    video_codec TEXT, audio_codec TEXT, bitrate REAL, has_audio INTEGER,
    probe_status TEXT DEFAULT 'pending',  -- pending/running/done/failed/skipped
    probe_attempts INTEGER DEFAULT 0,
    probe_error TEXT, probe_version TEXT,
    created_at REAL NOT NULL, updated_at REAL NOT NULL
);
-- 索引: media_id / fingerprint_full / fingerprint_quick
```

### asset_processing_state（阶段级状态机）

```sql
CREATE TABLE asset_processing_state (
    asset_id TEXT REFERENCES assets(asset_id) ON DELETE CASCADE,
    stage TEXT NOT NULL,                  -- probe/fingerprint/duplicate/scene/keyframe/
                                          -- asr/ocr/vision/labels/embedding
    status TEXT DEFAULT 'NEW',            -- NEW/PENDING/PROCESSING/DONE/PARTIAL/
                                          -- FAILED/SKIPPED/STALE/REVIEW
    pipeline_version TEXT, algorithm_version TEXT,
    model_name TEXT, model_version TEXT,
    input_fingerprint TEXT,               -- 处理时输入内容指纹
    started_at REAL, completed_at REAL,
    retry_count INTEGER DEFAULT 0,
    error_code TEXT, error_message TEXT,
    result_count INTEGER DEFAULT 0,
    reviewed INTEGER DEFAULT 0, reviewed_at REAL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (asset_id, stage)         -- 一个阶段一条状态，禁止重复
);
```

### processing_history（状态转移历史，只追加）

```sql
CREATE TABLE processing_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id TEXT, stage TEXT,
    old_status TEXT, new_status TEXT,
    reason TEXT,                           -- 为什么变（能回答"为什么今天又重跑 ASR"）
    model TEXT, version TEXT,
    created_at REAL NOT NULL
);
```

### asset_locations（位置追踪：移动/改名/多副本）

```sql
CREATE TABLE asset_locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id TEXT REFERENCES assets(asset_id) ON DELETE CASCADE,
    source_id INTEGER REFERENCES sources(id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL,
    media_id INTEGER REFERENCES media_files(id) ON DELETE CASCADE,
    first_seen REAL NOT NULL, last_seen REAL NOT NULL,
    current INTEGER DEFAULT 1,             -- 1=当前有效位置
    UNIQUE(source_id, relative_path)
);
```

---

## 3. 关键行为

### 移动/改名（不产生新 asset）
```
旧路径: Z:\新视频\123.mp4  →  新路径: Z:\客户入户\北京\123.mp4
内容 fingerprint 相同 → 复用 asset_id
→ asset_locations 插入新位置(current=1)，旧位置置 current=0
→ 全部 processing state / ASR / labels / embedding 原样保留
```

### 重复副本（同一内容多处）
```
clip_a.mp4 与 clip_a_duplicate.mp4 内容相同
→ 只建 1 个 canonical asset
→ asset_locations 记录 2 条位置
→ duplicate 阶段识别为重复组（不自动删除）
```

### 修改检测（内容变化 → STALE）
```
同路径 size/mtime/quick fingerprint 变化
→ 确认内容变化后，按依赖图将下游阶段标记 STALE
→ 重新进入处理队列
```

### MISSING/OFFLINE（不删数据）
```
硬盘未挂载/网络盘断开 → sources.online=0, media_files.available=0
asset / ASR / labels / embedding 全部保留
文件重新出现后自动恢复（available=1）
```

---

## 4. 一致性保证

- `asset_processing_state PRIMARY KEY(asset_id, stage)` → 一个阶段一条状态
- 内容协调：扫描时 quick fingerprint 已存在 → 复用 asset_id（`ensure_all_video_assets`）
- 一致性测试：同 fingerprint 只允许一个 canonical asset（`test_canonical_single_identity`）
- 分层哈希：`fingerprint_full` 仅疑似重复（同 quick 多 asset）或 ≥200MB 大文件才计算，避免 3TB 全量读盘

---

## 5. 账号/标签/模板解耦（全局命名规则）

```text
Asset ≠ Account ≠ Template ≠ Project
asset_id（素材） ← 独立
account_id（B001–B010）→ 仅出现在 projects 表（发布目标），不在标签/模板中
TC_CONTENT_TAGS（内容标签）→ 素材层
CT01–CT12（内容模板）→ 模板层，所有账号可复用
PRJ-xxx（视频项目）→ 项目层，绑定 account_id + template_id
```

未来扩展表（P2+，见 BACKLOG.md）：segments / keyframes / transcripts / ocr_text /
labels / embeddings / duplicate_groups / content_templates / projects /
project_segments / performance —— 全部通过 `asset_id` / `segment_id` 关联，不重复建身份。
