# TARGET_ARCHITECTURE.md — 树剪 AI素材生产工作台 目标架构（第二阶段）

> 日期：2026-08-19 | 定位：将现有树剪升级为 **AI Material Workbench（AI素材生产工作台）**
> 本文档是目标蓝图；实施顺序与验收见 `docs/PHASE2_IMPLEMENTATION_PLAN.md`。
> 关键决策：**以 v13 模块化架构为基底演进**，将 v12 已验证能力并入，而不是在 v12.1 平铺代码上重做。

---

## 1. 目标定位

```
原始素材（Z 盘 ~3TB / 4.6万视频，含网络盘）
    ↓ 扫描 + 资产化（P0/P1）
视频级/镜头级分析（元数据/场景/关键帧/ASR/OCR/视觉标签）
    ↓ 重复与成片/原片识别
SQLite 主库 + Faiss 向量索引 + FTS5 全文
    ↓ 自然语言/条件组合检索
内容模板（T01–T12，镜头槽位）
    ↓ 每槽位推荐 3–10 候选
人工选镜 → AI 辅助排序 → 自动粗剪 → 人工终检 → 导出
```

**核心原则（用户第二阶段总指令）**：
- 程序做 80% 机械工作，人做 20% 内容判断（不追求 100% 无人值守）
- 只读素材：不移动/不改名/不覆盖/不删除原视频；所有衍生数据进独立数据目录
- 允许上 GitHub 的只有开发资产（源码/Skill/模板/文档/配置模板/锁文件）；视频/模型/运行库/Secret 一律本地
- 不重新开发已稳定可用的功能（先审计 → KEEP/IMPROVE/REFACTOR/REMOVE_LATER/BROKEN/UNKNOWN）
- 每个处理阶段可断点续跑、可缓存、错误日志，禁止假测试（无真实证据不算成功）

## 2. 五大能力层（总指令 §5）

| 层 | 职责 | 对应模块（目标） |
|---|---|---|
| **Asset Layer** 素材资产层 | 多盘/网络盘扫描、文件指纹、元数据、增量登记、断点续扫 | `media/`（v13 source_discovery）+ `catalog/` + 任务队列 |
| **Understanding Layer** 素材理解层 | 场景切分、关键帧、ASR、OCR、成片/原片、重复识别、运营标签 | `analysis/` + `models/`（Florence/SenseVoice/YOLO/SigLIP）+ 规则分类器 |
| **Search Layer** 素材检索层 | SQLite FTS5 全文 + Faiss 向量 + 混合筛选 + 人工纠错回写 | `catalog/` + `models/semantic_matching` + 新 `search/` |
| **Template Layer** 模板驱动层 | T01–T12 模板（镜头槽位）、候选推荐、人工选镜 | 新 `templates/` + `matching/planning` |
| **Rough Cut Layer** 自动粗剪层 | 按模板切片/排序/时长/字幕草稿、导出草稿+MP4 | `production/`（v13 双输出）+ `output/` |

## 3. 目标模块结构（v13 演进版）

```
treecut/  （GitHub 开发资产仓库，保持私有或按用户决定）
├─ app/                # UI（桌面 + 本地 API）
├─ src/
│  ├─ platform/        # 能力探测、路径、硬件策略（v13 保留）
│  ├─ media/           # 扫描、ffprobe 探测、增量发现（v13 保留 + 增强断点）
│  ├─ catalog/         # 素材登记、资产主表、FTS5 全文索引（v13 增强）
│  ├─ database/        # SQLite 统一主库 + schema + migration（合并 v12 system.db 表）
│  ├─ models/          # 模型注册中心（v13）+ 新增 SigLIP 图文向量 + OCR
│  ├─ analysis/        # 抽帧/场景/ASR/OCR/视觉/成片原片/重复识别（v13 + 新增）
│  ├─ search/          # 语义检索（BGE-M3/SigLIP + Faiss）+ 混合筛选 + 人工纠错
│  ├─ templates/       # T01–T12 模板定义 + 槽位 + 候选推荐
│  ├─ matching/        # 可解释选材 + 时间线规划（v13）
│  ├─ production/      # 统一生成（MP4 + 剪映草稿 + 字幕 + 音乐）（v13）
│  ├─ quality/         # 输出质量回读（真实证据）（v13）
│  └─ learning/        # 反馈记录与规则/权重回写（v13）
├─ config/             # 配置模板（.example）、标签词典、模型配置
├─ templates/          # 模板 JSON 版本库（T01-v1, T01-v2…）
├─ dictionaries/       # B003 运营标签词典
├─ migrations/         # 数据库迁移脚本
├─ tests/  benchmarks/  docs/  scripts/  prompts/  workflows/
├─ README.md  PROJECT_STATE.md  models/manifest.json
└─ data/（仅本地，不入 Git）  # databases/ indexes/ keyframes/ thumbnails/
                             # proxies/ asr_cache/ ocr_cache/ models/ exports/
                             # roughcuts/ logs/ temp/ — 默认 E:\AI_DATA\treecut\（可配置）
```

## 4. 数据库目标 Schema（第二阶段总指令 §6 §10）

统一主库 `materials.db`（以 v13 catalog 库为基底，补齐总指令要求表）：

| 表 | 用途 | 来源 |
|---|---|---|
| `assets` | 视频级主表（asset_id UUID/内容hash、path、size、hash、duration、w/h、fps、codec、asset_type） | 新增（v12 materials + v13 media_files 合并） |
| `segments` | 镜头级（segment_id、asset_id、start_ms、end_ms、scene_no、quality_score） | 新增（scene_features 升级） |
| `keyframes` | 关键帧（frame_id、segment_id、timestamp、path、sharpness） | 新增（video_frames 升级） |
| `transcripts` | ASR 文本（raw + corrected 分离） | 新增（audio_features 升级） |
| `ocr_text` | 硬字幕/文字识别（text、bboxes、subtitle_flag、coverage） | 新增 |
| `labels` | 运营标签（label_type、value、confidence、source=rule/model/human） | 新增（tag_learning 升级） |
| `embeddings` | 向量引用（vector_ref、model、dim，不存 JSON 大字段） | 新增 |
| `duplicate_groups` | 精确/近重复分组 | 新增 |
| `tasks` | 断点续跑（status/retry/checkpoint/error） | v13 analysis_jobs 对齐 |
| `templates` / `template_slots` | 模板与槽位定义 | 新增 |
| `projects` / `project_segments` | 剪辑项目与选镜结果 | 新增 |
| `publications` / `performance` | 发布与投流数据（接小红书读取器） | 新增 |
| `manual_feedback` | 人工纠错（永远追加，不覆盖） | v13 feedback.db 对齐 |

## 5. 模型与检索目标

| 能力 | 目标方案 | 本机（6GB 显存）判断 | 替代 |
|---|---|---|---|
| 视频元数据 | FFmpeg/ffprobe（已装 8.1.1） | CPU 即可 | — |
| 场景切分 | PySceneDetect ContentDetector（先调阈值） | CPU 优先 | OpenCV 帧差（v12 插件已有降级） |
| ASR | faster-whisper small 先测中文，不足再 medium | 6GB 可跑 small；medium 需分批 | SenseVoice（CPU 已可用） |
| OCR 字幕 | PaddleOCR PP-OCRv5 / RapidOCR（已装 1.4.4） | CPU 可用 | RapidOCR |
| 图文向量/标签 | **SigLIP** siglip-base-patch16-224（零样本分类/检索） | 6GB 可跑，小 batch | BGE-M3（已装，dim 768 索引已建）+ CLIP |
| 向量索引 | Faiss CPU | 主要占 RAM | — |
| 文本检索 | SQLite FTS5 | CPU | — |
| 重复识别 | SHA256 精确 + pHash + embedding 近重复 | CPU+GPU 混合 | 先 hash 再向量 |
| 人物检测 | YOLO 轻量（yolov8n 已装 6.5MB） | CPU | SigLIP 标签兜底 |
| 视觉大模型 | Qwen3-VL 仅疑难片段按需；6GB 不常驻 | **本机不满足 10GB 门槛 → Florence 为默认** | Florence-2（CPU 已可用） |
| 离线 TTS | sherpa-onnx VITS（v13 已验证） | CPU | Edge TTS（联网备用） |
| 剪辑引擎 | FFmpeg（切片/拼接/音轨/字幕） | CPU/NVENC | — |

## 6. 关键设计决策（本阶段建议）

1. **代码基底 = v13**：GitHub 仓库同步升级到 v13 架构（`src/treecut/`），v12.1 平铺代码归档为 `legacy/` 或单独分支，不删除。
2. **数据库统一**：以 v13 `materials.db` 为演进主库，把 v12 `ai_material_library.db` 的 16143 条素材与 system.db 的 workflow 表迁移/合并；迁移前备份。
3. **检索离线固化**：默认 `HF_HUB_OFFLINE=1`，本地模型目录优先；缺失模型提示下载而非静默在线尝试。
4. **素材盘只读 + 断点**：扫描/分析全程不写 Z 盘；任务队列 checkpoint 持久化，网络盘超时不拖死（重试/跳过/记录）。
5. **新增表通过 migration**：所有 schema 变更走 `migrations/`，不手改生产库。
6. **人工纠错一等公民**：标签/类型/ASR/OCR/重复标记均可改，`manual_feedback` 永远追加，human 标签不被模型覆盖。
7. **模板先行 T01/T02**：先跑通两套模板（T01 小户型空间解决型、T02 真实客户伸缩案例型），再扩 T03–T12。
8. **GitHub 边界**：仓库只存开发资产；`models/manifest.json` 记录模型名/版本/来源/路径/hash，模型本体不 commit。

## 7. 目标非目标（V1 明确不做）

- ❌ 100% 无人值守自动剪辑（人是最终审美判断）
- ❌ AI 配音/复杂特效/自动花字/自动发布/人物替换（全部 LATER）
- ❌ 全量大型 VLM 逐帧分析（先场景切分→关键帧→小模型→疑难片段才用强模型）
- ❌ 用 AI 判断「好不好看」（quality_score 只做可解释的 sharpness/运动/曝光/重复/人物占比等）
- ✅ 目标：人工完成一条 25–50s 视频的时间从当前 4–5 小时明显下降（实测为准，不预设数字）

## 8. 风险与缓解

| 风险 | 缓解 |
|---|---|
| v13 未上 GitHub，仓库与真实版本脱节 | 第二阶段第一步先把 v13 源码纳入 Git 基线（D 部分） |
| 网络盘（Z:\\X1）IO 不稳定 | 断点续扫、IO 超时重试、缓存、并行度 2–6 控制 |
| 6GB 显存限制 | Florence 默认 + SigLIP small + ASR small/分批；Qwen 仅兜底 |
| 依赖版本混乱（requirements 锁旧版 vs 已装新版） | 用独立 venv + 固定 lock 文件，不污染系统 Python |
| 双数据库历史数据迁移风险 | 先备份 → 只读迁移 → 校验行数 → 切流 |
| v12 workflow 从未真实跑通 | 以 v13 生产链为正式链路，v12 workflow 不再作为运行入口 |
