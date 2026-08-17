# 树剪 TreeCut v10.3 — 软件规格说明

> **最后更新:** 2026-06-11 | **版本:** v10.4-beta (本次优化后)
> **用途:** 坤宝岛台品牌 AI 视频半自动剪辑工具

---

## 一、软件功能概述

### 已实现的核心功能

| 功能模块 | 描述 | 状态 |
|---------|------|------|
| AI 文案生成 | DeepSeek API 生成三段式（钩子→卖点→CTA）小红书风格口播文案 | [OK] |
| AI 配音 (TTS) | Edge TTS 引擎，支持中文 XiaoyiNeural/YunxiNeural 音色，保护词校验 | [OK] |
| 视频素材扫描 | 多文件夹递归扫描 .mp4，支持分类文件夹映射和关键词匹配 | [OK] |
| 素材智能匹配 | FAISS 向量检索 + 知识库规则 + SQL 关键词三层降级 | [OK] |
| 剪映草稿生成 | 生成 JianyingPro 兼容的 draft_content.json + draft_meta_info.json | [OK] |
| BGM 自动匹配 | 按视频主题（卖点/效果/工厂）匹配对应风格背景音乐 | [OK] |
| 视觉画面分析 | VisionModel 统一接口：Qwen3-VL → Florence-2 → Ollama(qwen2.5vl) 自动降级 | [OK] |
| 语音识别 | SenseVoice 优先 + Faster-Whisper large-v3 备用 | [OK] |
| 音频分类 | Librosa 启发式分析（音乐/人声/笑声/静音检测） | [OK] |
| 行业知识库 | 1200+ 岛台行业词汇分类器 + 石材/工艺/五金/风格专业知识库 | [OK] |
| 标签融合 | TagMerger 多模型标签置信度加权 + 同义词规范化 | [OK] |
| FAISS 向量索引 | 全量/增量重建，原子写入防并发冲突 | [OK] |
| 自学习引擎 | 定时分析使用记录 → DeepSeek 生成优化规则 → 自动调整权重 | [OK] |
| 素材质量控制 | 清晰度/稳定性/构图/时长/标签完整度评分 + 感知哈希去重 | [OK] |
| 使用记录收集 | 全局操作追踪（标注/生成/评分/错误），支持 CSV 导出 | [OK] |
| 批量生产 | 多卖点混剪 + Excel 脚本批量读取 + 进度跟踪 | [OK] |
| 全盘检索 | 快速扫描常用位置 + 文件夹浏览 + 视频元数据批量探测 | [OK] |
| 素材标注 | 流式抽帧+缩略图显示+实时AI标签+用户反馈学习 | [OK] |
| 配置热重载 | reload_config() 运行时刷新环境变量和 .env 配置 | [OK] |
| 重试与熔断 | 指数退避重试 + CircuitBreaker 熔断器 + 全局 BreakerRegistry | [OK] |
| 安全模块 | API Key 脱敏/检测/原子写入 + 敏感字段递归过滤 | [OK] |
| 桌面 UI | ttkbootstrap darkly 主题，7 个 Tab + 菜单 + 快捷键 | [OK] |
| Web UI | Gradio Web 控制台，可选 Token 认证 | [OK] |

### 本次优化新增/修复

| 项目 | 描述 |
|------|------|
| Bug修复 ×9 | 重复按钮栏删除、不存在函数修复、属性名修正、路径错误修复 |
| 性能优化 ×2 | SentenceTransformer 模型缓存、重复代码提取 |
| 死代码清理 | 类外方法移除、重复 import 删除 |
| 代码重构 | audio_models.py 提取公共 `_extract_audio()` 函数 |
| 字段修正 | analyzer.py duration 从文件大小(MB)改为真实视频时长(秒) |
| 状态命令修复 | show_status() 改用 LibraryBuilder 替代不存在的 ai_material_library |

---

## 二、技术架构

### 分层架构图（文字描述）

```
┌─────────────────────────────────────────────────┐
│              入口层 (树剪.py)                    │
│  --desktop / --web / --cli / --setup / --status  │
├──────────┬──────────┬──────────┬────────────────┤
│  UI 层   │  Web 层  │  CLI 层  │  工具层         │
│ desktop  │  web.py  │ CLI args │  setup_wizard   │
│ annot.   │  Gradio  │          │  review_audit   │
│ library  │          │          │  auto_upgrade   │
│ settings │          │          │                 │
├──────────┴──────────┴──────────┴────────────────┤
│              核心引擎层 (core/)                   │
│  pipeline  │ copywriter │ tts   │ draft  │ config│
│  analyzer  │ vision_unified │ audio_models       │
│  classifier (1200+词) │ tag_merger               │
│  frame_annotator │ frame_extractor               │
│  library_builder │ self_learning_engine          │
├─────────────────────────────────────────────────┤
│              AI 服务层                            │
│  DeepSeek API │ Edge TTS │ Ollama │ Transformers │
│  FAISS │ SentenceTransformer │ librosa │ faster-whisper│
├─────────────────────────────────────────────────┤
│              知识 & 数据层                        │
│  utils/knowledge.py │ material_engine_v3/        │
│  SQLite ×5 (ai_material_library.db / usage / ...) │
│  FAISS 索引文件                                   │
└─────────────────────────────────────────────────┘
```

### 模块清单及职责

| 路径 | 职责 | 状态 |
|------|------|------|
| `树剪.py` | 程序入口，CLI 参数解析，路由分发 | 活跃 |
| `core/__init__.py` | 核心引擎导出，Windows 编码修复，.env 加载 | 活跃 |
| `core/config.py` | 80+全局配置参数，路径/视频/音频/字幕/TTS/功能开关 | 活跃 |
| `core/pipeline.py` | 主生成管道：素材收集→文案→配音→匹配→BGM→草稿 | **核心** |
| `core/copywriter.py` | DeepSeek 三段式文案生成 + 画面描述提取 + CTA 检测 | 活跃 |
| `core/tts.py` | Edge TTS 配音生成 + 文本清洗 + 保护词校验 + 字幕拆分 | 活跃 |
| `core/draft.py` | 剪映草稿 JSON 构建 (JianyingDraftBuilder) + 保存/备份 | 活跃 |
| `core/analyzer.py` | 视频多模型并行分析调度器 (抽帧→视觉→音频→融合) | 活跃 |
| `core/vision_unified.py` | 统一视觉模型接口 (Qwen3/Florence/Ollama 自动选择) | 活跃 |
| `core/audio_models.py` | 音频识别 (Whisper + AudioClassifier) + 情绪/事件检测 | 活跃 |
| `core/classifier.py` | 1200+岛台行业词汇三级分类器 + 同义词映射 | 活跃 |
| `core/tag_merger.py` | 多模型标签置信度加权融合 + 同义词规范化 | 活跃 |
| `core/frame_extractor.py` | FFmpeg 抽帧 + 关键帧选择 | 活跃 |
| `core/frame_annotator.py` | 流式全帧标注引擎 (抽帧+显示+识别+反馈学习) | 活跃 |
| `core/library_builder.py` | SQLite 入库 + FAISS 索引全量/增量构建 (原子写入) | 活跃 |
| `core/deepseek_client.py` | DeepSeek API 统一封装 (文案/标签优化/权重调整/故障排查) | 活跃 |
| `core/self_learning_engine.py` | 定时自学习 (分析记录→生成规则→自动应用) | 活跃 |
| `core/usage_recorder.py` | 全局操作记录收集 (标注/生成/评分/错误) + CSV 导出 | 活跃 |
| `core/drive_scanner.py` | 全盘/快速扫描 + 视频元数据批量探测 | 活跃 |
| `core/batch_evaluator.py` | 批量自我评估 | 辅助 |
| `core/bgm_matcher.py` | BGM 智能匹配 | 辅助 |
| `core/multimodal_embedding.py` | 多模态密集字幕生成 | 辅助 |
| `core/topic_discovery.py` | 自动主题发现 | 辅助 |
| `core/learner.py` | 反馈学习模块 | 辅助 |
| `ui/desktop.py` | ttkbootstrap 桌面主窗口 (7 Tab + 菜单 + 进度 + 快捷键) | **核心** |
| `ui/frame_annotation.py` | 素材标注 Tab (驱动树+视频列表+帧卡片+反馈) | 活跃 |
| `ui/library_tab.py` | AI素材库管理 Tab (扫描/分析/FAISS重建) | 活跃 |
| `ui/settings_page.py` | 统一设置页 (AI配置/使用记录/素材识别/视频生成/质量控制/AI助手) | 活跃 |
| `ui/web.py` | Gradio Web 控制台 | 活跃 |
| `ui/virtual_scroll.py` | 虚拟滚动组件 | 辅助 |
| `utils/knowledge.py` | 岛台行业知识库桥接 (石材/工艺/五金/风格/岛台类型) | 活跃 |
| `utils/quality_scorer.py` | 素材质量评估+过滤+去重 (清晰度/稳定性/构图/标签完整度) | 活跃 |
| `utils/retry.py` | 指数退避重试 + 熔断器 + 全局 BreakerRegistry | 活跃 |
| `utils/security.py` | 安全加固 (API Key脱敏/泄漏检测/安全文件读写) | 活跃 |
| `utils/logging.py` | 统一日志模块 | 辅助 |
| `utils/silent_subprocess.py` | 静默子进程封装 | 辅助 |
| `utils/model_downloader.py` | 模型下载工具 | 辅助 |
| `material_engine_v3/` | V3素材引擎 (与 core/ 功能重叠，建议合并) | **待合并** |
| `tests/` | 单元测试 (test_core/test_core_functions 等 5 个文件) | **需扩展** |
| `review_audit.py` | 双程序检索复查复盘系统 | 工具 |
| `setup_wizard.py` | 首次配置向导 | 工具 |
| `auto_upgrade.py` | 自动升级脚本 v10.3→v10.4-beta | 工具 |

---

## 三、已知问题与限制

### 严重 (需尽快修复)

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| 1 | `material_engine_v3/` 与 `core/` 功能高度重叠（两套 vision/analyzer/smart_matcher） | 架构级 | 维护困难，代码冗余 |
| 2 | 5 个独立 SQLite 数据库无统一连接管理 | 数据层 | 资源泄漏风险 |
| 3 | 1200+关键词逐一遍历 O(n×m)，classifier 性能瓶颈 | `core/classifier.py` | 分类速度慢 |
| 4 | CLIP/YOLO 模块标记为保留但未实现（始终为 None/空列表） | `core/analyzer.py` | 功能不完整 |

### 中等 (建议优化)

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| 5 | 配置模块 80+ 全局变量，无类型校验 | `core/config.py` | 维护困难 |
| 6 | `desktop.py` 561 行，内联大量 lambda 和线程逻辑 | `ui/desktop.py` | 可读性差 |
| 7 | 大量 `except: pass` 和 `except Exception: pass` 吞没错误 | 全局 | 调试困难 |
| 8 | `run()` 和 `run_multi()` 约 80% 逻辑重复 | `core/pipeline.py` | 代码冗余 |
| 9 | `reload_config()` 与模块顶层初始化高度重复 | `core/config.py` | 维护困难 |

### 低 (后续关注)

| # | 问题 | 位置 |
|---|------|------|
| 10 | 模型降级链仅按文件存在性判断，未健康检查 | `core/vision_unified.py` |
| 11 | TTS 可能在已运行的事件循环中调用 `asyncio.run()` 报错 | `core/tts.py` |
| 12 | UI 快捷键 Ctrl+R 行为与当前 Tab 不一致 | `ui/desktop.py` |
| 13 | 代码中英文混杂，不利于开源 | 全局 |
| 14 | 测试覆盖率不足（无 UI 测试/集成测试） | `tests/` |

---

## 四、未来优化方向

### 短期 (v10.5)

1. **合并 material_engine_v3** → 将独特功能（数据库 schema migration）迁入 core/，废弃 v3 子模块
2. **统一数据库管理** → DatabaseManager 连接池 + 上下文管理器
3. **关键词匹配加速** → Aho-Corasick 自动机替代逐一遍历
4. **提取公共草稿生成方法** → 消除 run()/run_multi() 80% 重复
5. **配置模块重构** → Pydantic Settings 或 dataclass 单例

### 中期 (v11.0)

6. **实现 CLIP/YOLO 集成** → 完善多模型融合管道
7. **向量数据库迁移** → Chroma/Milvus 替代 FAISS+JSON 映射
8. **异步管道** → asyncio 替代 ThreadPoolExecutor，提升并发效率
9. **UI 拆分** → 每个 Tab 独立文件，提取 ScrollableFrame/ThreadManager 公共组件
10. **测试扩展** → pytest fixtures + UI 自动化测试，目标覆盖率 > 60%

### 长期

11. **CI/CD 流水线** → GitHub Actions: lint(ruff/mypy) → test → build(PyInstaller) → release
12. **国际化** → 统一中英文注释/变量名规范
13. **插件系统** → 支持第三方视觉/音频模型扩展
14. **云同步** → 草稿/素材库云端备份与多设备同步

---

## 五、运行环境要求

| 组件 | 最低要求 | 推荐 |
|------|---------|------|
| Python | 3.10+ | 3.12 |
| GPU | 无 (CPU 可运行) | NVIDIA 8GB+ VRAM |
| RAM | 8GB | 16GB+ |
| 磁盘 | 5GB (不含模型) | SSD 50GB+ |
| 外部依赖 | FFmpeg, Ollama (可选) | Ollama + Qwen2.5VL:7B |
| 模型下载 | Whisper large-v3 (~3GB), Qwen3-VL (~8GB) | SenseVoice (~200MB) |

### Python 依赖

```
openai>=1.0, edge-tts, pyJianYingDraft, ttkbootstrap,
gradio, faiss-cpu, sentence-transformers, faster-whisper,
librosa, opencv-python, numpy, Pillow, python-dotenv,
schedule, openpyxl, transformers, torch
```

---

## 六、快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key
# 方式A: 环境变量
set DEEPSEEK_API_KEY=sk-your-key-here

# 方式B: .env 文件
echo DEEPSEEK_API_KEY=sk-your-key-here > .env

# 3. 首次配置向导
python 树剪.py --setup

# 4. 启动桌面应用
python 树剪.py

# 5. 命令行快速生成
python 树剪.py --cli 内嵌烤箱 --tts --auto-bgm

# 6. Web 控制台
python 树剪.py --web
```

---

*文档自动生成于 2026-06-11 代码分析优化过程。*
