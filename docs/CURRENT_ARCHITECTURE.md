# CURRENT_ARCHITECTURE.md — 树剪 TreeCut 当前架构（第二阶段审计基线）

> 日期：2026-08-19 | 审计者：DeepSeek Harness（第二阶段第一轮）
> 依据：真实代码阅读 + 真实运行测试 + 真实数据库/模型/素材盘检查。所有结论均有证据，未验证项明确标注 UNVERIFIED。

---

## 0. 执行摘要

树剪项目当前存在**两套并存代码与两套数据库体系**，这是第二阶段必须首先正视的结构性事实：

| 体系 | 代码位置 | 架构 | 数据库 | 状态 |
|---|---|---|---|---|
| **v12.1 平铺版** | `C:\Users\admin\github\treecut`（GitHub 公开仓库）＝ `E:\树剪整理\01_主程序源码\树剪软件相关文件`（真实运行环境，代码 hash 完全一致） | 单目录平铺 `core/` + `ui/` + `plugins/` | `ai_material_library.db`（GUI/分析，16143 素材）+ `data/db/system.db`（v3 workflow，全空） | 主仓库代码；GUI 分析链真实产生过 16143 条素材数据 |
| **v13 模块化版** | `E:\树剪整理\02_安装程序\TreeCut_v13`（打包安装版，**未上 GitHub**） | `src/treecut/` 分层模块（platform/catalog/models/analysis/matching/production/quality/feedback） | `runtime_data/database/materials.db`（15378 媒体）+ jobs.db + feedback.db | **本机可真实运行**（v13.5.10，Florence 就绪，36 份升级文档，61 项测试）；开发版，未完成全量商业验收 |

**核心判断**：v13 是「新房迁移」——它已经把 v12 的真实能力迁入一条清晰生产链，并诚实标记了 v12 的假模块；GitHub 仓库仍停留在 v12.1 平铺架构。第二阶段的目标架构应**以 v13 为基底继续演进**，而不是在 v12.1 平铺代码上重做一遍 v13 已解决的问题。

---

## 1. 程序入口与启动方式

| 入口 | 文件 | 说明 | 测试 |
|---|---|---|---|
| 桌面 GUI | `树剪.py` → `launch_desktop()` → `ui/desktop.py TreeCutApp` | tkinter 主窗口，7+ 标签页 | import 通过；GUI 曾崩溃（`_crash_latest.txt`：`NameError: free variable 'e'`，E 盘旧环境） |
| CLI | `树剪.py --cli 关键词` → `core.run()` | 单条生成 | 模块可 import |
| Web 控制台 | `树剪.py --web` → `ui/web.py build_ui()` | Gradio，端口 7860 | 模块可 import |
| 状态 | `树剪.py --status` | LibraryBuilder 统计 | 已运行验证 |
| REST API | `api_server.py`（FastAPI v13，端口 8000） | 任务提交/查询/搜索/配额 | **routes=10 可加载**，但依赖 `core.auth_middleware` |
| v13 入口 | `TreeCut_v13\src\treecut\main.py`（`-m treecut.main`） | `--status/--drives/--scan/--catalog-scan` 等 | **真实运行成功**（v13.5.10） |

## 2. 语言与技术栈

- **主语言**：Python 3.12.10（requirements.txt 锁定版本与已装版本严重不一致，见 §9 风险）
- **GUI**：tkinter（v12.1 平铺版）；v13 为自研桌面（`ui/desktop.py`）
- **视频**：FFmpeg 8.1.1（`E:\` 与 PATH 均有）；decord 0.6.0；opencv-python；ffmpeg-python；scenedetect 0.7（requirements 锁 0.6.4）
- **AI 模型**（真实环境 `models/` 与 HF 缓存已确认）：Florence-2-base（441.8MB，CPU 可推理）、Qwen3-VL-4B-Instruct-FP8（约 5.7GB，需 10GB 显存）、SenseVoiceSmall（CPU 中文识别）、faster-whisper large-v3/small（缓存有，v13 标记未就绪）、YOLOv8n（6.5MB）、BGE-M3（HF 缓存有）、CLIP（vit-base-patch32）、sherpa-onnx VITS 离线 TTS（v13）
- **向量检索**：faiss-cpu（真实索引 `shipin/material_bge_m3.index` 63MB、`material_faiss.index` 2.3MB）+ sentence-transformers（BGE-M3）
- **数据库**：SQLite（多库，见 §5）
- **剪映集成**：pyJianYingDraft（`core/draft.py` JianyingDraftBuilder，**真实构建成功**）

## 3. 模块地图（v12.1 平铺版，GitHub 仓库）

```
树剪.py / main.py / launcher.pyw   ← 入口
api_server.py / receive.py         ← REST 接口
core/                              ← 核心引擎（43 个模块）
  ├─ config.py / config_v2.py / config_loader.py   ← 配置（三套并存！）
  ├─ database.py                   ← 数据库单例（GUI）+ execute_sql（v3 workflow）
  ├─ pipeline.py (62KB)            ← 主生成管道 run/run_multi/run_batch（6 步）
  ├─ workflow_engine.py            ← v3.0 工作流（断点续跑，18 节点）
  ├─ analyzer.py                   ← 视频分析（抽帧→视觉→音频→融合标签）
  ├─ video_scanner.py / drive_scanner.py  ← 素材扫描（GUI 后台扫描）
  ├─ frame_extractor.py / frame_annotator.py ← 抽帧与标注
  ├─ audio_models.py               ← SenseVoice/Whisper/音频分类
  ├─ vision_unified.py             ← 统一视觉入口
  ├─ smart_matcher_v3.py           ← FAISS+BGE-M3 语义检索（核心）
  ├─ smart_match_engine.py / clip_matcher.py ← 自适应匹配/CLIP 重排
  ├─ script_learning.py / script_understanding.py / copywriter.py / tts.py / draft.py
  ├─ tag_merger.py / classifier.py / library_builder.py
  ├─ event_bus.py / retry_scheduler.py / review_queue.py / quality_center.py
  ├─ self_learning_engine.py / learner.py / deepseek_client.py / usage_recorder.py
  └─ orchestrator.py / smart_orchestrator.py / batch_evaluator.py / bgm_matcher.py …
ui/desktop.py (100KB) / ui/tabs/ / ui/components/   ← tkinter 界面
plugins/recognize|quality|correct   ← 14 个插件（workflow 执行单元）
tasks/task_queue.py                 ← 批量任务队列
material_engine_v3/                ← 旧素材引擎（smart_matcher/queue/schema）
material_engine_v5/                ← v5 占位（仅 scene_checkpoint.json）
dashboard/app.py                   ← Streamlit 看板
scripts/ tests/ config/ data/      ← 脚本/测试/配置/数据
```

### v13 模块地图（安装版，未上 GitHub）

```
src/treecut/
  bootstrap.py / main.py / api.py / desktop.py / watchdog.py / scheduler.py / maintenance.py
  platform/   能力探测、路径、硬件策略（capabilities.py, crash.py）
  media/      probe.py（ffprobe）、source_discovery.py（增量素材发现）
  catalog/    library/catalog.py（增量登记）、classification.py
  models/     registry.py（模型状态中心）、vision_florence.py、vision_qwen.py、
              speech_sensevoice.py、speech_whisper.py、tts_local.py（sherpa-onnx）、
              semantic_matching.py、object_detection.py
  analysis/   worker.py、pool.py、parallel.py（正式分析队列）
  application/ production.py（统一生产服务）、jobs.py
  output/     jianying.py、mp4.py、narration.py、cover.py、filters.py
  quality/    质量回读（真实证据）
  learning/   feedback.py
  config/     settings.py
```

## 4. 数据流（当前实际行为）

### 4.1 GUI 素材分析链（v12.1，真实产生数据）
```
选择目录（ui/desktop 后台扫描）
→ drive_scanner/video_scanner 枚举视频（Z:\ 网络盘）
→ analyzer.analyze():
    抽帧 extract_by_interval(1s, max 60)
    → 关键帧选择 _select_key_frames(6)
    → 并行视觉 _run_vision（VisionModel = Qwen3/Florence/Ollama）
    → 并行音频 _run_whisper + _run_audio_classifier
    → tag_merger.merge 融合标签
    → 入库 materials / video_registry / analysis_log
```
- 真实库证据：`materials` 16143 行（analyzed=1），`video_registry` 6745 行，`analysis_log` 756 行（models_used=qwen_vl,clip,whisper,yolo），`video_annotations` 39 行，`video_frames` 20 行，`learned_scripts` 126 行，`generation_video_log` 9 行，`generation_material_log` 57 行，`task_log.db` 6740 行（全部 done，2026-06-08 批量）

### 4.2 生成链（v12.1 pipeline.run 6 步）
```
关键词 → 1 素材扫描 collect_multi_point_mp4s
       → 2 文案（脚本库/AI/直传）
       → 3 配音 TTS（edge-tts zh-CN-XiaoyiNeural）
       → 4 素材匹配 ai_match_clips（SmartMatcher FAISS）/ opening 池 / 人像过滤 / 质量过滤 / 去重
       → 5 BGM 选择
       → 6 剪映草稿 JianyingDraftBuilder + 字幕时间轴
```

### 4.3 v13 生产链（验收记录确认）
```
素材登记 → 真模型分析（Florence/SenseVoice/YOLO）→ 风险筛选
→ 卖点匹配 → 时间线规划 → 配音/字幕/音乐 → MP4/剪映草稿
→ 质量回读（ffprobe/解码/音量/字幕像素证据）→ 用户反馈
```

## 5. 数据库体系（三库并存，关键风险）

| 数据库 | 位置 | 内容 | 真实数据 | 使用方 |
|---|---|---|---|---|
| `ai_material_library.db` | 项目根 | materials/video_registry/video_annotations/video_frames/learned_scripts/generation_*/analysis_log 等 25 表 | **16143 素材、6745 注册、756 分析** | GUI 分析/生成（v12.1 Database 单例） |
| `data/db/system.db` | data/db | materials/scene_features/audio_features/subtitle_features/quality_results/tasks/task_queue 等 9 表 | **全空（0 行）** | v3.0 WorkflowEngine/插件（execute_sql） |
| `material_usage.db` | 项目根 | usage | 68 行 | 素材使用追踪 |
| `task_log.db` | 项目根 | task_log | 6740 行 | 批量任务记录 |
| v13 `materials.db` | TreeCut_v13/runtime_data/database | media_files(15378)/analysis_jobs(4347)/sources(11)/media_tags(0) | **15378 媒体、4347 任务** | v13 catalog/analysis |
| v13 `jobs.db` / `feedback.db` | 同上 | production_jobs(2) / material_feedback(0) | 少量 | v13 生产/反馈 |

**关键发现**：
1. **WorkflowEngine 引用的表（scene_features/audio_features/subtitle_features/quality_results/tasks）只存在于全空的 system.db**，而 `ai_material_library.db` 没有这些表 → v3 workflow 链从未在真实素材上跑通过（0 行证据）。
2. GUI 分析链（materials 16143 行）与 workflow 链（system.db 空）**没有打通**——这是「分析→质检→纠错→归档」闭环缺失的直接证据。
3. v13 用独立 `materials.db`（15378 媒体），与 v12 的 `ai_material_library.db` 又是两套。

## 6. 模型与检索现状（实测）

| 项 | 状态 | 证据 |
|---|---|---|
| FAISS 索引 | ✅ 存在 | `shipin/material_bge_m3.index` 63MB（dim=768, ntotal=756）、`material_faiss.index` 2.3MB |
| 语义检索 | ✅ **离线可用** | 实测 `SmartMatcher.search('抽屉 收纳')` 离线模式返回 3 条正确相关素材（郴州付小姐抽屉/收纳案例） |
| 检索降级风险 | ⚠️ | 未设 `HF_HUB_OFFLINE` 时尝试从 hf-mirror 在线下载 BGE-M3，网络失败则检索 0 结果 |
| 视觉模型 | ✅ Florence 真实推理（CPU）；⚠️ Qwen3-VL 需 10GB 显存（本机 6GB 不满足，回退 Florence） | v13 status: florence_ready=true, qwen_vl_ready=false |
| 语音识别 | ⚠️ SenseVoice CPU 可用；Whisper 权重在缓存但 v13 标记「未就绪」（TLS 下载失败历史） | v13 验收记录 |
| 离线 TTS | ✅ sherpa-onnx VITS 真实合成中文 WAV（v13） | v13 验收记录 |
| 场景切分 | ⚠️ scenedetect 0.7 实测对静态样片 0 切点；workflow 插件有帧差法降级 | 网络盘样片读取抖动，需在稳定环境复测 |

## 7. 真实素材盘现状（第二阶段 P0 扫描对象）

| 目录 | 视频数 | 大小 | 备注 |
|---|---|---|---|
| `Z:\未处理素材` | 16788 | 1219 GB | 最大未处理池 |
| `Z:\新视频-张育豪` | 1692 | 1158 GB | |
| `Z:\装修素材2` | 18250 | 272.7 GB | |
| `Z:\已处理素材` | 6430 | 206.1 GB | 卖点展示类（v12 已分析来源） |
| `Z:\B组更新视频` | 360 | 32.5 GB | 已发布成片 |
| `Z:\装修素材` | 1619 | 11.6 GB | |
| 其他（装修混剪/草稿等） | ~50 | ~3.5 GB | |
| **合计** | **~46159** | **~2.9 TB** | **Z 为网络映射盘（\\X1\素材01）** |

> ⚠️ **网络盘风险**：实测 Z 盘读取存在间歇超时（同一路径一次可读、一次不可读）。第二阶段必须：断点续扫 + 不因 IO 超时拖死程序 + 扫描进度持久化。

## 8. 已真实运行验证清单（B 部分）

| 验证项 | 结果 | 说明 |
|---|---|---|
| `import core` | ✅ | 版本 12.1.0 |
| 数据库初始化 | ✅ | ai_material_library.db 25 表可查 |
| 14 插件注册 | ✅ | recognize 5 + quality 6 + correct 3 |
| FastAPI 服务加载 | ✅ | 10 routes |
| tkinter UI import | ✅ | 可加载（历史有崩溃记录） |
| ffprobe 元数据 | ✅ | 实测样片 duration/resolution/fps/bitrate 正确 |
| 抽帧 | ✅ | 实测 6 帧 jpg 成功 |
| 剪映草稿构建 | ✅ | draft content 完整（含 tracks/materials） |
| 数据库写入 | ✅ | 临时库完整字段插入成功（`start_time` 等 NOT NULL 需全字段） |
| FAISS+BGE-M3 检索 | ✅ | 离线 3 条相关结果 |
| 场景切分 | ⚠️ | 静态样片 0 切点（需稳定盘复测） |
| v13 `--status` | ✅ | v13.5.10，Florence 就绪，CPU profile |

## 9. 主要问题清单（按 KEEP/IMPROVE/REFACTOR/REMOVE_LATER/BROKEN/UNKNOWN 分类）

### KEEP（保留直接使用）
- 剪映草稿生成（pyJianYingDraft 实测可用）
- 视频抽帧（FrameExtractor 实测可用）
- Florence 画面分析（CPU 真实推理）
- SenseVoice 中文识别（CPU 可用）
- YOLOv8n 物体/人物检测
- FAISS + BGE-M3 语义检索（离线可用，但需固化离线开关）
- Edge TTS（联网备用）/ sherpa-onnx 离线 TTS（v13）
- v13 增量素材发现、磁盘身份/盘符变化重连、任务断点恢复（v13 已验证）

### IMPROVE（有价值但需增强）
- **双数据库统一**：ai_material_library.db 与 system.db（workflow 表）合并为单一主库 + 增量迁移
- **SmartMatcher 离线固化**：默认 `HF_HUB_OFFLINE=1` + 本地模型目录探测，去掉在线下载依赖
- **任务队列**：task_log.db 有 6740 条真实记录 → 升级为 status/retry/checkpoint 完整断点续跑（v13 已做，v12 需对齐）
- **素材扫描**：v12 drive_scanner（GUI 后台扫描）→ 对接 v13 source_discovery 增量扫描
- **生成管线**：v12 pipeline 6 步 → 复用 v13 production 服务（双输出 MP4+草稿）

### REFACTOR（逻辑有问题需局部重构）
- **配置三套并存**（config.py / config_v2.py / config_loader.py）→ 统一
- **分析器重复**：VideoAnalyzer 与 SmartVideoAnalyzer 职责重叠 → 合并（v13 已合并）
- **调度器重复**：orchestrator 与 smart_orchestrator 两套 → 合并（v13 已合并）
- **models 引用分散**：模型加载散落多处 → v13 model registry 统一

### REMOVE_LATER（价值低但先不删）
- `material_engine_v3/`（旧引擎，smart_matcher 逻辑已迁 core）
- `material_engine_v5/`（仅 scene_checkpoint.json 占位）
- `dashboard/app.py`（Streamlit 看板，未确认使用）
- 各种一次性迁移脚本（_gen_excel.py/_split_export.py/_deploy.py 等）

### BROKEN（当前无法工作）
- v12.1 **workflow 全链路**：system.db 全空，scene_features 等表无数据 → 质检/纠错/归档闭环未真实跑通
- `_crash_latest.txt` 记录 GUI 崩溃（NameError: free variable 'e'）——E 盘旧环境

### UNKNOWN（无法验证）
- Qwen3-VL 在 6GB 显存台式机的真实速度/质量（v13 明确要求目标机验收）
- 剪映不同版本草稿兼容性
- 大规模素材分类准确率基准（缺标注集）
- scenedetect 在大规模真实素材上的切点质量（网络盘不稳定未完整复测）

---

## 10. 审计方法说明
- 代码阅读：GitHub 仓库（C:\Users\admin\github\treecut）与真实运行环境（E:\树剪整理\01_主程序源码\树剪软件相关文件）关键文件 hash 逐一比对（10/10 SAME）→ 两处代码一致。
- 运行测试：模块 import、FastAPI 加载、插件注册、ffprobe、抽帧、草稿构建、FAISS 检索、v13 status 均在本机实际执行。
- 数据审计：读取 4 个 SQLite 库 schema 与行数（真实证据）。
- 模型/素材盘：检查 models/、HF 缓存、shipin/ 索引、Z 盘 11 个目录（视频数/GB）。
- 本报告为只读审计，**未修改任何业务代码**；Git 基线与实施计划见 docs/PHASE2_IMPLEMENTATION_PLAN.md 与 reports/phase2_01_treecut_audit.md。
