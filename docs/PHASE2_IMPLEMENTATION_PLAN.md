# PHASE2_IMPLEMENTATION_PLAN.md — 树剪 AI素材生产工作台 第二阶段实施计划

> 日期：2026-08-19 | 本计划对应第二阶段总指令 P0–P7 Gate 顺序。
> **本文件是计划，不是已执行代码**。每阶段必须：读现状 → 计划 → Branch → 最小实现 → 单元测试 → 集成测试 → 真实样片测试 → Benchmark → 更新文档 → Git commit → Push。**没有测试 = NOT DONE。**

---

## 0. 总原则（每阶段固定流程）

```
Read current state → Plan → Branch → Minimal implementation → Unit test
→ Integration test → Real sample test → Benchmark → Update docs
→ Update PROJECT_STATE.md → git diff → Commit → Push Private GitHub
```

Gate 顺序（总指令 §39）：P0 架构审计+Git基线 → P1 扫描+SQLite+Task Queue → P2 场景+关键帧+ASR+OCR → P3 成片/原片+去重+标签 → P4 FTS5+SigLIP+Faiss+检索 → P5 T01/T02 模板推荐 → P6 人工选镜+粗剪 → P7 扩展 T03–T12。
**禁止跳级**（P1 未稳定不开发 P7）。

---

## P0 架构审计 + Git 安全基线（当前进行中）

**已完成**（本第一轮）：
- ✅ 代码审计：v12.1（仓库+真实环境，代码一致）+ v13（安装版，未上 Git）双架构盘点
- ✅ 真实运行测试：import/插件/API/UI/ffprobe/抽帧/草稿/FAISS 检索/v13 status（证据见 CURRENT_ARCHITECTURE.md §8）
- ✅ 数据审计：4 个 SQLite 库 schema+行数；Z 盘 11 目录 ~4.6万视频 ~2.9TB
- ✅ 输出：docs/CURRENT_ARCHITECTURE.md、docs/TARGET_ARCHITECTURE.md、reports/phase2_01_treecut_audit.md

**待用户确认后执行**：
- [ ] 决定 GitHub 仓库归属：当前 `yuhao8977-stack/treecut` 为**公开**仓库（用户此前要求公开）。总指令要求 Private。→ 需用户确认：保持公开 / 转私有 / 新建私有仓库。
- [ ] 将 v13 源码（E:\树剪整理\02_安装程序\TreeCut_v13\src\treecut + docs + runtime 说明）纳入 Git 基线
- [ ] Secret 复查：确认 .env 不入库（当前 .gitignore 已含 .env ✅）、models_manifest 只记录清单
- [ ] baseline commit `treecut-legacy-baseline`（v12.1 现状）+ 新建开发 branch（如 `phase2/v1`）
- [ ] Git 大文件复查（当前 188 个跟踪文件，无 >100MB 视频/模型 ✅，需复扫确认）

## P1 扫描 + SQLite 统一库 + 任务队列（断点续跑）★最先做

**目标**：让程序可靠跑起来（P0 稳定基础，1–2TB 目录可中断续跑、不重复处理）

1. **扫描器**：以 v13 `source_discovery` 为基础，支持多目录（本地盘+Z 网络盘），递归遍历 + 扩展名白名单（mp4/mov/mkv/avi/m4v/webm），不移动原文件
2. **文件指纹**：SHA256/xxhash 大文件分块哈希 → 精确重复识别
3. **元数据**：ffprobe 读取 duration/resolution/fps/codec/bitrate/orientation，异常文件跳过并记录
4. **统一 SQLite**：创建 `assets` 主表（asset_id=UUID+hash），从 v12 `ai_material_library.db`（16143 条）只读迁移 + 从 v13 `materials.db`（15378 条）合并；迁移前备份到 backups/
5. **任务队列**：status(pending/running/done/failed/skipped)+retry_count+error+started_at+finished_at+model_version+pipeline_version；Windows 重启/崩溃可续；文件未变化+模型版本未变化→直接缓存
6. **IO 容错**：网络盘超时重试、跳过、记录；并行 2–6 路防机械盘 IO 打满

**验收**：Z 盘抽样目录（建议 10–50GB 或 100–500 条代表视频）扫描可中断后续跑；重复启动不重复处理已完成文件；损坏文件不拖死。

### ✅ P1 已完成（2026-08-19，实现在独立仓库 `yuhao8977-stack/treecut-v13`）

- **扫描器**：复用 v13 `Catalog.scan`（增量、符号链接防护、扩展名白名单、网络盘支持）— 实测通过
- **文件指纹**：新增 `library/hash_utils.py`（完整流式 SHA256 4MiB 分块 + size/首尾 1MiB 快速指纹）
- **元数据**：新增 `library/assets.py` assets 表 + `probe_worker.py`（ffprobe 采集 duration/resolution/fps/codec/audio，PATH 回退）
- **统一 SQLite**：assets 表（asset_id=UUID+指纹），`--migrate-v12` 从 v12 库只读迁移（备份先行、标签导入、缺失跳过）
- **任务队列**：probe_status(pending/running/done/failed/skipped)+attempts+error；`recover_interrupted_probes()` 崩溃后自动收回；`max_probe_attempts=3` 重试上限
- **IO 容错**：损坏文件 3 次重试后 skipped 不拖死；网络盘超时走 catalog 重试
- **实测**：真实 4K HEVC mov / 1080x1080 h264 成片元数据正确；重复文件完整 SHA256 一致；v13 生产库 0 修改（15378 行不变）
- **测试**：`tests/` 6 项 pytest 全通过（hash/assets/重试上限/中断恢复/迁移只读+标签/缺失库）
- **文档**：`docs/P1_SCAN_ASSETS.md`（v13 仓库）
- **遗留**：Z 网络盘全量扫描待 Z 盘可用时执行（10–50GB 小目录起步）；并行 worker（2–6 路）为 P1.1 增强项

## P2 场景切分 + 关键帧 + ASR + OCR（镜头级资产化）

1. **场景切分**：PySceneDetect ContentDetector，先调阈值（v12 配置 scene_change_threshold=25）；保存 segments(start_ms/end_ms/scene_no)；禁止逐帧大模型
2. **关键帧**：每 segment 2–5 帧（首/中/尾 + 清晰度/差异度），存 JPG/WEBP 到 cache，DB 只记录路径
3. **ASR**：faster-whisper small 先测中文岛台口播，不准再 medium；保存 raw transcript + corrected 分离、时间戳、语言、置信度、model_version
4. **OCR/硬字幕**：RapidOCR/PaddleOCR 只对关键帧+必要抽样帧；输出 text/bboxes/subtitle_flag/coverage；用于成片识别

**验收**：真实样片 100 条抽检：切点可人工抽查；每段 2–5 帧覆盖内容；中文转写可抽查；能区分成片字幕与原素材。

## P3 成片/原片识别 + 重复/近重复 + 运营标签（B003 体系）

1. **成片/原片/半成品**：综合硬字幕比例+切镜频率+BGM+口播完整度+时长+片头尾+字幕区域 → asset_type+confidence+reason_codes；≥0.90 自动、0.60–0.89 待审、<0.60 UNKNOWN；建立 100–200 条人工评估集
2. **重复识别三级**：L1 SHA256 精确 → L2 pHash+时长+关键帧 → L3 embedding 近重复（换字幕/封面/轻剪）；输出 duplicate_group/type/similarity（HIGH/REVIEW/LOW）；**不自动删除**
3. **B003 运营标签**：场景/状态/功能/工艺/使用/材质/镜头/人物 8 类；首期 20–40 个高频标签（伸缩/抽屉/收纳/插座/烤箱/海棠角/封边/全景/无人等）；SigLIP 零样本 + 词典；动作标签（伸缩/旋转/抽屉开）必须看 segment 首中尾帧+运动变化，不能单帧判断
4. **人工纠错**：manual_feedback 追加记录；human 标签不被模型覆盖

**验收**：人工抽检 200 条成片/原片准确率 >90% 为目标；重点标签 Top-K 可用；100 组重复样本识别。

## P4 SQLite FTS5 全文 + SigLIP 图文向量 + Faiss + 混合检索

1. **FTS5**：对 ASR/OCR/标签/路径/文件名/人工备注建全文索引（SQLite 内嵌，无需服务）
2. **图文向量**：SigLIP siglip-base-patch16-224（813MB，6GB 可跑小 batch）；每 segment 一个 embedding；Faiss CPU 索引（先 IndexFlatL2，后续可 IndexIVF）
3. **混合检索**：Query → Hard Filter（asset_type=RAW/person=NO/时长/标签）→ Semantic Recall → Metadata Rerank → Quality → Duplicate Penalty → Top K；返回每条候选的解释（客户家:0.94 全景:0.88 无人:TRUE…）
4. **离线固化**：默认 HF_HUB_OFFLINE=1 + 本地模型目录，缺失提示下载

**验收**：「客户家 无人 全景 伸缩岛台」等真实运营 Query，Top5 至少 2–3 个候选可用；关键词检索毫秒/秒级。

## P5 T01/T02 模板系统 + 候选推荐

1. **模板定义**：template_id/name/version/content_goal/user_problem/target_duration/slots（order/purpose/min-max_duration/required_tags/preferred_tags/avoid_tags/shot_type/semantic_query）；版本化（T01-v1、T01-v2 并存不覆盖）
2. **首期两套**：T01 小户型空间解决型（8 槽位）、T02 真实客户伸缩案例型（8 槽位）
3. **候选推荐**：每槽 3–10 候选 = Required Tags 匹配 + 语义相似度 + Shot Type + 质量分 − 重复惩罚；V1 不伪造表现权重；每条候选显示推荐原因（可解释，非黑盒）

**验收**：选 T01 后每槽自动给 3–10 候选；Top5 中至少 2–3 个可用。

## P6 人工选镜 + AI 辅助排序 + 自动粗剪

1. **选镜 UI**：SELECT/BACKUP/EXCLUDE 写入 project_segments；AI 不能自动代替最终选择
2. **AI 辅助排序**（仅在人工选镜后）：建议顺序/每镜时长/前 3 秒最强镜/重复提示/备选，只建议不直接改
3. **自动粗剪**：FFmpeg 按 project+template+selected segments 生成 rough_cut.mp4 + timeline.json + cuts.csv + subtitles.srt；每段可追溯 asset_id/segment_id/source_path/start_ms/end_ms
4. **字幕**：ASR 生成 SRT 草稿供人工修改；检测到硬字幕提示 HARD SUBTITLE DETECTED，默认不叠完整字幕

**验收**：真实 T01 项目走通「选镜→粗剪→剪映/播放器检查」；人工只需替换/微调；不产生黑帧。

## P7 扩展模板与数据闭环

- 扩 T03–T12（尺寸避坑/清单型/收纳/大横厅/布局对比/有娃/风格/工艺/用电/嵌入电器）
- publications/performance 关联（接小红书笔记读取器导出的发布数据与投流数据）
- 表现回流：按模板/素材/标签统计「更易跑量/获客」，用于推荐加权（有真实数据后才启用）

**验收**：能回答「哪个模板/镜头/标签更易跑量」。

---

## 里程碑与验收指标（总指令 §37 §44）

| 指标 | 目标 |
|---|---|
| 扫描 | 万级文件稳定；不重复分析；可中断恢复；损坏文件不拖死 |
| 成片/原片 | 人工抽检准确率 >90%（目标，实测为准） |
| 标签 | 重点标签 Top3 Recall 可用，人工可一键修正回写 |
| 搜索 | 真实运营 Query Top5 至少 2–3 可用 |
| 模板 | 不需人工重新翻硬盘 |
| 粗剪 | 人工完成一条 25–50s 视频时间较当前 4–5 小时明显下降（实测） |
| V1 完成条件 | 扫描/增量/断点/切分/关键帧/ASR/OCR/成片原片/去重/标签/纠错/全文/向量/混合筛选/T01/T02/候选/选镜/粗剪/Git 版本化 共 20 项全满足 |

## 测试与 Benchmark 体系（总指令 §36）

- 20–50 条搜索 Query（真实运营用语）
- 100–200 条成片/原片标注集
- 重点标签正负样本（每类 ≥50）
- 100 组重复/近重复样本
- T01/T02 真实模板项目各 1
- 四层测试：单元 / 模块集成 / 完整工作流 / 真实用户验收（v13 已有 61 项自动测试作基底）

## 数据目录（本地，不入 Git，可配置，不硬编码盘符）

```
E:\AI_DATA\treecut\（默认，可配置）
  source_media/（仅路径映射，不移动原素材）
  databases/ indexes/ keyframes/ thumbnails/ proxies/
  asr_cache/ ocr_cache/ models/ exports/ roughcuts/ logs/ temp/
```

## 风险与 Gate 决策点

1. **GitHub 仓库可见性**：公开 vs 私有（用户此前要求公开；总指令要求私有）→ **P0 必须用户拍板**
2. **代码基底**：本计划假设以 v13 演进。若用户希望保留 v12.1 平铺代码继续开发，需重估 P1 迁移成本（v13 已解决的大部分问题会退回）
3. **Z 盘网络盘**：P1 扫描器必须先在小目录（10–50GB）实测网络盘 IO 稳定性再全量
4. **依赖环境**：用独立 venv + requirements/phase2 锁文件（requirements/phase2_optimize.txt 已有雏形），不污染系统 Python
5. **Qwen GPU 验收**：需在带 NVIDIA 显卡台式机完成（当前 6GB 机器不满足 10GB 门槛，默认 Florence）

## 立即停止点（本第一轮范围）

本计划仅覆盖到 P0 审计+Git 基线。**收到「继续第二阶段P1」前，不修改任何业务代码。**
