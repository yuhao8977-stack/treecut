# P1 扫描 + 统一资产库 + 任务队列（断点续跑）

> 第二阶段 P1 实现说明（2026-08-19）。基于 v13 Catalog 增量扫描能力扩展。

## 新增模块（src/treecut/library/）

| 模块 | 职责 |
|---|---|
| `hash_utils.py` | 大文件分块 SHA256（完整流式 + 首尾快速指纹） |
| `assets.py` | `assets` 资产表（asset_id=UUID+指纹）、ffprobe 元数据、probe 任务队列（断点续跑/重试上限） |
| `migrate_v12.py` | 从 v12 `ai_material_library.db` **只读**迁移素材身份（路径/指纹/标签），迁移前自动备份 |
| `probe_worker.py` | ProbeWorker：领取 pending/failed 任务 → ffprobe 元数据 + 完整 SHA256 → 落库 |

## 新增 CLI 命令（treecut.main）

```
--catalog-scan PATH    增量登记素材目录（v13 已有）
--probe-assets COUNT   采集 COUNT 个素材的 ffprobe 元数据 + 完整指纹（P1 新）
--assets-status        显示资产表状态（P1 新）
--assets-list [LIMIT]  列出资产（--probed-only 仅已探测）（P1 新）
--migrate-v12 V12_DB   从 v12 库只读迁移（P1 新）
```

## 端到端用法

```powershell
# 1. 扫描素材目录（增量，可中断续跑）
$env:TREECUT_DATA_ROOT = "E:\AI_DATA\treecut"      # 非 C 盘（v13 硬约束）
$env:TREECUT_MODEL_ROOT = "E:\AI_DATA\treecut\models"
python -m treecut.main --catalog-scan "Z:\装修素材"

# 2. 采集元数据 + 指纹（断点续跑：重复运行自动续）
python -m treecut.main --probe-assets 100

# 3. 查看资产状态
python -m treecut.main --assets-status
```

## 断点续跑设计（第二阶段 §7 硬性要求）

- `claim_probe()`：事务（BEGIN IMMEDIATE）领取 pending/failed 任务并置 running，attempts+1
- `complete_probe()/fail_probe()`：成功/失败落库；失败达到 `max_probe_attempts`（默认 3）后置 `skipped` 不再重试
- `recover_interrupted_probes()`：ProbeWorker 启动时自动把崩溃遗留的 running 收回为 pending（Windows 重启/进程被杀后继续）
- 文件未变化（size+mtime 一致）+ 模型版本未变化 → 扫描直接缓存跳过（Catalog 已有逻辑）

## 重复识别（第一阶段精确重复）

- `fingerprint_quick`：size + 首尾 1MiB（扫描期廉价去重）
- `fingerprint_full`：完整流式 SHA256（4MiB 分块，内存 O(4MiB)）
- `assets` 表按 `fingerprint_full` 建索引，`stats()["exact_duplicates"]` 报告精确重复数
- 只标记不删除（总指令：不自动删除任何视频）

## 测试

```powershell
python -m pytest tests/ -v
# 6 项：hash_utils / assets 建表 / 重试上限 / 中断恢复 / v12 迁移只读+标签 / 缺失库报错
```

实测（真实视频）：4K HEVC mov（3840x2160）、1080x1080 h264 成片 ffprobe 元数据正确；
损坏文件 3 次重试后 skipped 不拖死流程；重复文件完整 SHA256 一致。
