# 树剪 TreeCut v11.1 — 持续优化架构计划

## 当前状态 (2026-06-11)

```
82/82 文件编译通过
4 核心模型强制集成 (Qwen3-VL-4B, SenseVoice, Whisper, FAISS+BGE-M3)
8 个基础设施模块已创建并集成
```

---

## 架构分层

```
┌─────────────────────────────────────────────────┐
│  入口层                                          │
│  树剪.py → CLI分发 → desktop/web/cli/setup       │
├─────────────────────────────────────────────────┤
│  调度层 (已创建, 部分集成)                        │
│  core/orchestrator.py  ← 统一模型入口             │
│  core/batch_scheduler.py ← 多线程批量             │
├─────────────────────────────────────────────────┤
│  业务层                                          │
│  core/pipeline.py     ← 主生成管道                │
│  core/config_v2.py    ← 配置中心 (已导出到__init__)│
│  core/database.py     ← 数据库 (已导出到__init__)  │
│  core/script_learning.py ← 脚本学习库             │
├─────────────────────────────────────────────────┤
│  AI 增强层 (已创建, 部分集成)                      │
│  core/clip_matcher.py ← CLIP图文重排 (已接入pipeline)│
│  core/script_understanding.py ← 语义解析 (已接入pipeline)│
│  utils/retry.py       ← 重试熔断 (已接入DeepSeek) │
│  utils/model_downloader.py ← 模型下载 (待接入orchestrator)│
├─────────────────────────────────────────────────┤
│  UI 层                                           │
│  ui/desktop.py        ← 主窗口 (7标签页)          │
│  ui/settings_page.py  ← 设置页 (延迟加载)         │
│  ui/components/       ← 可复用组件                │
└─────────────────────────────────────────────────┘
```

---

## 集成状态

| 模块 | 状态 | 接入点 |
|------|:--:|------|
| `utils/retry.py` | ✅ 已集成 | `core/deepseek_client.py:_call()` 通过 `call_with_retry()` 自动重试 |
| `core/clip_matcher.py` | ✅ 已集成 | `core/pipeline.py:ai_match_clips()` FAISS匹配后 CLIP 重排序 |
| `core/script_understanding.py` | ✅ 已集成 | `core/pipeline.py:run()` Step 4 FAISS为空时语义解析增强 |
| `core/batch_scheduler.py` | ✅ 已集成 | `ui/desktop.py:_run_batch()` 替换串行循环为多线程调度 |
| `core/config_v2.py` | ✅ 已导出 | `core/__init__.py` 可通过 `from core import config_v2` 访问 |
| `core/database.py` | ✅ 已导出 | `core/__init__.py` 可通过 `from core import database` 访问 |
| `core/orchestrator.py` | ✅ 已导出 | `core/__init__.py` 可通过 `from core import orchestrator` 访问 |
| `utils/model_downloader.py` | ⬜ 待接入 | `core/orchestrator.py:load_all()` 模型缺失时自动下载 |

---

## 持续优化路线图

### Phase 7: 完全迁移到统一架构 (本周)

1. **analyzer.py → orchestrator**
   ```python
   # 旧: self.vision = VisionModel(); self.whisper = WhisperModel()
   # 新: from core import orchestrator; orch.analyze_image(...); orch.analyze_audio(...)
   ```

2. **全部 sqlite3.connect → database.get_connection()**
   ```python
   # 旧: with sqlite3.connect(str(db_path)) as conn: ...
   # 新: from core import database; with database.get_connection() as conn: ...
   ```

3. **全部 os.environ.get → config_v2**
   ```python
   # 旧: SELLING_POINT_DIR = os.environ.get("TREECUT_SELLING_DIR", "Z:\\...")
   # 新: from core import config_v2; config_v2.get("SELLING_POINT_DIR")
   ```

### Phase 8: 学习闭环完整化 (下周)

1. **自动评分**: 每次 run() 完成后自动记录 usage_records
2. **每日分析**: SelfLearningEngine 定时运行脚本分析 + 模型权重优化
3. **动态权重**: 分析结果自动更新 TagMerger._weights，下次生成生效

### Phase 9: 多行业扩展 (本月)

1. **KnowledgeBridge 多行业**: 从 JSON 加载不同行业知识库
2. **模型自动下载**: orchestrator 检测缺失模型 → 调用 model_downloader
3. **GPU 自动检测**: batch_scheduler 根据显存动态调整并发数

### Phase 10: 生产环境优化 (下月)

1. **数据库分库**: 热数据/冷数据分离 → archive_db.py 定时归档
2. **FAISS IVF 索引**: IndexFlatL2 → IndexIVFFlat (支持增量添加)
3. **WebSocket 实时进度**: Web UI 升级为实时推送生成进度
4. **CD 自动构建**: GitHub Actions → PyInstaller → Release

---

## 技术债务清单

| # | 项 | 优先级 | 预计工时 |
|---|------|:--:|:--:|
| 1 | analyzer.py → orchestrator 迁移 | P1 | 2h |
| 2 | 全局 sqlite3 → database 迁移 | P1 | 3h |
| 3 | 全局 os.environ → config_v2 迁移 | P2 | 2h |
| 4 | model_downloader 接入 orchestrator | P2 | 1h |
| 5 | 学习闭环完整化 | P2 | 4h |
| 6 | 增加 `__all__` 到 config/copywriter/tts/draft | P3 | 0.5h |
| 7 | 13+ 单例模式统一为装饰器 | P3 | 1h |
