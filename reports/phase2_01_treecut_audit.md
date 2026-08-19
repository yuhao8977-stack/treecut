# 第二阶段第一轮报告：树剪项目审计（phase2_01_treecut_audit）

> 日期：2026-08-19 | 执行：DeepSeek Harness（接续「小红书笔记读取器本机自主」对话第二阶段）
> 范围：**只读审计 + Git 基线准备，未修改任何业务代码**。所有结论附真实证据，未验证项标注 UNVERIFIED。

---

## 一、结论速览

| 项 | 结论 |
|---|---|
| 程序入口 | v12.1：`树剪.py`/`main.py`/`launcher.pyw`（tkinter GUI + CLI + Gradio Web）+ `api_server.py`（FastAPI）；v13：`src/treecut/main.py`（桌面+API 统一） |
| 主语言/栈 | Python 3.12.10 + FFmpeg 8.1.1 + SQLite + faiss-cpu + pyJianYingDraft；模型：Florence/Qwen3-VL/SenseVoice/Whisper/YOLO/BGE-M3/Sherpa TTS |
| 扫描 | v12 `drive_scanner`/`video_scanner`（GUI 后台扫描）；v13 `source_discovery`（增量，盘符变化重连） |
| 抽帧 | ✅ 真实可用（实测 6 帧成功） |
| ASR | ⚠️ SenseVoice CPU 可用；Whisper 权重在缓存但 v13 标记未就绪 |
| OCR | 代码有 RapidOCR 依赖（已装 1.4.4），未见真实大规模使用证据（UNVERIFIED） |
| 视觉模型 | ✅ Florence CPU 真实推理（v13 status 确认）；⚠️ Qwen3-VL 需 10GB 显存（本机 6GB 不满足） |
| 分类 | v12 tag_merger 规则融合 + v13 正式分类器；无大规模标注集基准（UNVERIFIED 准确率） |
| 剪辑 | ✅ 剪映草稿真实生成（pyJianYingDraft 实测）；v13 双输出 MP4+草稿 |
| 数据库 | **双体系断裂**：GUI 库 16143 素材（真实）vs workflow 库 system.db（全空 0 行）→ 质检/纠错/归档闭环从未真实跑通 |
| 缓存 | v12 `cache_manager` 两级缓存 + v13 runtime_data/cache |
| 任务队列 | v12 `task_queue` + task_log.db 6740 条真实记录；v13 analysis_jobs 4347 条（带断点恢复） |
| 重复识别 | 无专门实现（pipeline 有简单已用素材去重）；v13 有增量发现但重复分组未建（MISSING） |
| 成片/原片判断 | v12 无；v13 有风险筛选雏形；完整 asset_type 分类未实现（MISSING） |
| 向量检索 | ✅ FAISS+BGE-M3 **离线实测可用**（'抽屉 收纳' 返回 3 条正确相关素材） |
| 人工纠错 | v12 annotation_feedback/tag_learning 表存在但 0 行（未真实使用）；v13 feedback.db 0 行（MISSING 实际闭环） |
| 素材盘 | Z 网络盘（\\X1\素材01）~4.6万视频 ~2.9TB（未处理 1219GB + 新视频 1158GB + 装修素材2 272GB…） |
| 代码版本 | GitHub 仓库与真实环境关键文件 10/10 hash 一致（v12.1）；**v13 未上 GitHub（双架构分叉）** |

**总体判定**：`PHASE 2 AUDIT COMPLETE — v13 为演进基底，v12.1 归档保留。`（详见下方四类清单）

---

## 二、执行过程摘要

1. **定位项目**：`C:\Users\admin\github\treecut`（GitHub 公开仓库，188 文件）= `E:\树剪整理\01_主程序源码\树剪软件相关文件`（真实运行环境，含模型/素材/活跃数据库）；`E:\树剪整理\02_安装程序\TreeCut_v13`（打包安装版 v13.5.10，未上 Git）。
2. **代码审计**：阅读入口、core 43 模块、pipeline(1309 行)、workflow_engine、smart_matcher_v3、analyzer、14 插件、v13 全套 `src/treecut` + 36 份升级文档；双环境关键文件 hash 比对（10/10 SAME）。
3. **真实运行测试**：import core ✅、14 插件注册 ✅、FastAPI 10 routes ✅、tkinter UI import ✅、ffprobe 元数据 ✅（11.87s/720x1280/60fps）、抽帧 6 帧 ✅、剪映草稿构建 ✅、临时库写入 ✅、**FAISS+BGE-M3 离线检索 ✅**（3 条正确相关素材）、v13 `--status` ✅（v13.5.10, florence_ready）。
4. **数据审计**：4 个 SQLite 库全表行数（见 §四）；Z 盘 11 目录视频数/GB 统计。
5. **安全与资产边界**：真实 `.env` 含 DEEPSEEK_API_KEY（已确认 .gitignore 排除，未入库）；GitHub 仓库 188 文件无 >100MB 大文件、无媒体/模型权重；`.gitignore` 已覆盖 .env/媒体/模型/DB（上一阶段 GITHUB_ASSET_BOUNDARY_VERIFIED 的延续）。

---

## 三、对当前功能的四类判定（KEEP / IMPROVE / REFACTOR / REMOVE_LATER / BROKEN / UNKNOWN）

### ✅ KEEP（保留直接使用，已验证）
| 功能 | 证据 |
|---|---|
| 剪映草稿生成 | pyJianYingDraft 实测构建成功（tracks/materials 完整） |
| 视频抽帧 | FrameExtractor 实测 6 帧 jpg |
| ffprobe 元数据 | 实测 duration/resolution/fps/bitrate 正确 |
| Florence 画面分析 | v13 status florence_ready=true（CPU 真实推理） |
| SenseVoice 中文识别 | v13 验收记录：真实识别 |
| YOLOv8n 检测 | 模型 6.5MB 在库，v13 接入 |
| FAISS+BGE-M3 语义检索 | **实测离线返回正确相关素材**（需固化离线开关） |
| Edge TTS / sherpa-onnx 离线 TTS | v13 真实合成中文 WAV（44.1kHz/3.96s） |
| v13 增量素材发现/盘符重连/断点恢复 | v13 验收记录（36 份升级文档） |

### 🔧 IMPROVE（有价值需增强）
- 双数据库统一（ai_material_library.db 16143 条 + system.db workflow 表 + v13 materials.db 15378 条 → 单主库）
- SmartMatcher 离线固化（默认 HF_HUB_OFFLINE=1）
- 任务队列升级（task_log 6740 条真实数据 → status/retry/checkpoint 完整断点续跑）
- 素材扫描对接 v13 增量扫描（网络盘容错）

### 🔨 REFACTOR（逻辑问题需局部重构）
- 配置三套并存（config.py/config_v2.py/config_loader.py）
- VideoAnalyzer 与 SmartVideoAnalyzer 职责重叠（v13 已合并）
- orchestrator 与 smart_orchestrator 两套调度（v13 已合并）
- 模型加载散落 → v13 model registry 统一

### 🗑️ REMOVE_LATER（价值低先不删）
- material_engine_v3/（旧引擎）、material_engine_v5/（仅占位）
- dashboard/app.py（Streamlit，未确认使用）
- 一次性迁移脚本（_gen_excel.py/_split_export.py/_deploy.py 等）

### 💥 BROKEN（当前无法工作）
- **v12.1 workflow 全链路**：system.db 全空（0 行），scene_features/audio_features/subtitle_features/quality_results/tasks 表无数据 → 质检→纠错→复检→归档闭环从未真实跑通
- GUI 崩溃历史：`_crash_latest.txt`（NameError: free variable 'e'，E 盘旧环境）
- 语义检索在**未设离线开关**时：尝试在线下载 BGE-M3，网络失败则返回 0 结果

### ❓ UNKNOWN（无法验证）
- Qwen3-VL 在 6GB 显存台式机的真实表现（v13 要求目标机 GPU 验收）
- 剪映不同版本草稿兼容性
- 大规模素材分类准确率（无标注集）
- scenedetect 在真实大规模素材上的切点质量（Z 盘网络 IO 不稳定，静态样片 0 切点，需稳定盘复测）

---

## 四、数据库与素材盘实况（真实证据）

### ai_material_library.db（v12 GUI 主库，24MB）
materials **16143** / video_registry **6745** / analysis_log **756**（qwen_vl,clip,whisper,yolo）/ video_annotations 39 / video_frames 20 / learned_scripts **126** / generation_video_log 9 / generation_material_log 57 / script_material_preference 33 / tag_learning 0 / annotation_feedback 0 / compute_cache 0 …

### data/db/system.db（v3 workflow 库）
9 表全空（0 行）→ workflow 未真实使用

### material_usage.db / task_log.db
usage 68 / task_log **6740**（全部 done，2026-06-08 批量处理 Z:\B组更新视频）

### v13 runtime_data（TreeCut_v13）
materials.db（47MB）：media_files **15378** / analysis_jobs **4347** / sources **11** / media_tags 0；jobs.db production_jobs 2；feedback.db 0

### 素材盘（Z 网络盘 \\X1\素材01，3.2TB 已用 / 12.8TB 可用）
未处理素材 16788 视频 1219GB ｜ 新视频-张育豪 1692 视频 1158GB ｜ 装修素材2 18250 视频 272.7GB ｜ 已处理素材 6430 视频 206.1GB ｜ B组更新视频 360 视频 32.5GB ｜ 装修素材 1619 视频 11.6GB ｜ 其他 ~50 视频 3.5GB ｜ **合计 ~46159 视频 ~2.9TB**

### 模型（真实环境 models/ + HF 缓存）
Florence-2-base 441.8MB ✅ ｜ Qwen3-VL-4B-FP8 5.7GB ⚠️(需10GB显存) ｜ SenseVoiceSmall ✅ ｜ faster-whisper large-v3/small（缓存，v13 标记未就绪）｜ BGE-M3 ✅（dim768 索引 63MB, 756 向量）｜ CLIP vit-base ✅ ｜ YOLOv8n 6.5MB ✅ ｜ sherpa-onnx TTS ✅

---

## 五、Git 基线状态与待办（D 部分）

**现状**：
- GitHub 仓库 `yuhao8977-stack/treecut`（**公开**），main 分支，3 commits（8dfa5c0 初始 → 76a0b7b 同步缺失 → a8fbc5f git边界修复），工作树 clean
- 188 个跟踪文件；无 >100MB 大文件；无媒体/模型/DB/Secret（上一阶段边界验收延续）
- 真实运行环境**无 .git**（纯运行数据目录）

**待执行（需用户确认后）**：
1. **仓库可见性决策**：用户此前明确要求「公开」，第二阶段总指令要求「Private」→ 冲突，需用户拍板（保持公开 / 转私有 / 新建私有仓库）
2. v13 源码纳入 Git 基线（新增 `src/treecut/` + docs/，或作为独立仓库）
3. baseline commit `treecut-legacy-baseline`（v12.1 现状快照，可回滚点）
4. 新建开发分支（建议 `phase2/v1`）
5. 复扫 Secret/大文件（.env 已排除 ✅）

---

## 六、遗留事项（需用户决定）

1. **GitHub 可见性**：公开 or 私有（§五）
2. **代码基底**：确认以 v13 演进（推荐），还是保留 v12.1 平铺代码开发（成本更高）
3. **v13 是否上 GitHub**：作为同仓库分支、子目录，还是独立仓库
4. **treecut 历史 commit 中的旧音频记录**：上一阶段已 `git rm --cached`，历史彻底清除需 filter-repo + force push（公开仓库影响大，默认不做）
5. **Qwen GPU 验收时机**：如目标机是带 NVIDIA 台式机，P2/P3 前需完成

---

## 七、下一步

第一阶段已完成（Harness 审计增强，见 `C:\Users\admin\harness_workspace\reports\`）。本第一轮为第二阶段 P0（审计+基线），**到此停止**。
用户回复「继续第二阶段P1」后，按 `docs/PHASE2_IMPLEMENTATION_PLAN.md` 实施 P1（扫描 + SQLite 统一库 + 任务队列断点续跑）。
