# 树剪 TreeCut v11.1 — 架构重构完成报告

## 重构时间: 2026-06-11

---

## 新架构图

```
┌─────────────────────────────────────────────────┐
│          入口层 (树剪.py / ui/desktop.py)        │
└───────────┬─────────────────────────────────────┘
            │
┌───────────▼─────────────────────────────────────┐
│  统一调度层 (core/orchestrator.py)               │
│  ┌─────────────┬──────────────┬────────────────┐│
│  │ Qwen3-VL-4B │ SenseVoice   │ SmartMatcher   ││
│  │ (视觉)      │ + Whisper    │ (FAISS+BGE-M3) ││
│  │             │ (音频)       │                ││
│  └─────────────┴──────────────┴────────────────┘│
└─────────────────────────────────────────────────┘
            │
┌───────────▼─────────────────────────────────────┐
│  核心业务层 (core/)                              │
│  • pipeline.py    — 生成管道                     │
│  • config_v2.py   — 配置中心 (单例+观察者)       │
│  • database.py    — 数据库 (单例+CM)             │
│  • script_learning.py — 脚本学习库               │
│  • batch_scheduler.py — 批量调度器               │
│  • self_learning_engine.py — 自学习引擎           │
│  • script_utils.py — 统一脚本分割                │
│  • script_understanding.py — 语义解析            │
└─────────────────────────────────────────────────┘
            │
┌───────────▼─────────────────────────────────────┐
│  UI 层 (ui/)                                     │
│  • theme.py            — 颜色/字体常量           │
│  • components/         — 可复用组件              │
│    ├── folder_selector.py                       │
│    ├── progress_panel.py                        │
│    └── script_input_area.py                     │
│  • desktop.py          — 主窗口 (7+标签页)       │
│  • settings_page.py    — 设置页 (动态权重+AI助手)│
└─────────────────────────────────────────────────┘
```

## 新增核心类及职责

| 类 | 文件 | 职责 |
|---|------|------|
| `Config` | `core/config_v2.py` | 全局配置单例 (get/set/observe/reload/to_dict) |
| `Database` | `core/database.py` | 统一数据库访问 (CM + 预置表 + 业务方法) |
| `Orchestrator` | `core/orchestrator.py` | 强制模型调度 (load_all/analyze_image/analyze_audio/match_clips/health_check) |
| `BatchScheduler` | `core/batch_scheduler.py` | 多线程批量调度 (queue + workers + progress) |
| `ScriptLibrary` | `core/script_learning.py` | 脚本 CRUD + 向量检索 + 批量导入 |
| `ScriptParser` | `core/script_understanding.py` | DeepSeek 语义解析 + 规则降级 |
| `FolderSelector` | `ui/components/folder_selector.py` | 可复用文件夹选择器 |
| `ProgressPanel` | `ui/components/progress_panel.py` | 进度条组件 |
| `ScriptInputArea` | `ui/components/script_input_area.py` | 批量粘贴组件 |

## 已删除/替代的文件

| 文件 | 原因 |
|------|------|
| `material_engine_v3/core/vision_v2.py` | Dead — 无生产调用 |
| `material_engine_v3/core/vision_manager.py` | Dead — 仅 auto_labeler 使用 |
| `material_engine_v3/core/auto_labeler.py` | Dead — 无生产调用 |
| `backup_*/vision_models.py` | 旧版视觉模型 — 已被 VisionModel 替代 |
| ~80 行重复代码 (config.py reload) | 提取 `_init_config_vars()` |

## 数据库表一览

| 表 | 用途 |
|---|------|
| `materials` | 素材元数据 (16,143条) |
| `video_registry` | 视频注册 (6,744条) |
| `analysis_log` | 分析记录 (756条) |
| `annotation_feedback` | 标注反馈 |
| `tag_learning` | 标签学习 |
| `learned_scripts` | 脚本学习库 |
| `generation_log` | 生成记录 |
| `model_calls` | 模型调用记录 (新增) |

## 已知遗留问题

1. **embedding 覆盖率**: 16,143条素材仅756条(4.7%)有 embedding — 需批量生成
2. **sensevoice 中文路径**: funasr C++层不支持中文路径 — 使用 temp dir workaround
3. **FAISS C++ 中文路径**: 同上有 workaround
4. **学习闭环**: usage_records 仅有测试记录 — 需实际使用触发
5. **Windows GBK 编码**: 部分模块需要 UTF-8 stdout reconfigure

## 后续优化建议

1. 使用 Chroma/Milvus 替代 FAISS + JSON idmap
2. 实现异步管道 (asyncio) 替代 ThreadPoolExecutor
3. CI/CD: GitHub Actions → lint → test → build → release
4. 插件系统: 支持第三方模型扩展
5. 云同步: 草稿/素材库云端备份
