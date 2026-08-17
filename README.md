# 树剪 TreeCut —— 半自动剪辑程序（代码仓库）

> 本仓库仅包含 **代码、配置与文档**。模型（约 7GB）与素材不在仓库内（原因与获取方式见下文）。

## 📁 仓库内容说明

| 路径 | 说明 |
|------|------|
| `main.py` / `树剪.py` / `launcher.pyw` | 程序入口与启动器 |
| `api_server.py` / `receive.py` | 接口服务 |
| `core/` `ui/` `dashboard/` | 核心模块 / 界面 |
| `config/` `data/` | 配置与数据 |
| `scripts/` `tasks/` `tests/` | 脚本 / 任务 / 测试 |
| `material_engine_v3/` `material_engine_v5/` | 素材引擎 |
| `requirements.txt` `Dockerfile` `docker-compose.yml` | 依赖与部署 |
| `CHANGELOG.md` `DEPLOY.md` `ARCHITECTURE_PLAN.md` `SOFTWARE_SPECIFICATION.md` | 项目文档 |
| `models_manifest.txt` | **模型清单**（见下） |

## 🚀 快速开始

1. 安装依赖：`pip install -r requirements.txt`
2. 下载模型：运行 `Modelscope下载模型.bat` 或 `download_models.py`（清单见 `models_manifest.txt`）
3. 启动：`python launcher.pyw`（或 `python main.py`）

## 🤖 模型获取说明

模型体积约 **7GB**，远超 GitHub 单文件限制（100MB），因此**未纳入版本控制**。完整清单见 `models_manifest.txt`，主要模型：

| 模型 | 大小 | 用途 | 下载脚本 |
|------|------|------|----------|
| Qwen3-VL-4B-Instruct-FP8 | ~5.7GB | 视觉理解 | `dl_model.bat` |
| SenseVoiceSmall | ~893MB | 语音识别 | `dl_sensevoice.bat` |
| Florence-2-base | ~442MB | 图像理解 | `download_models.py` |

下载后放入 `models/` 目录，运行 `verify_models.py` 校验。

## ⚠️ 注意事项

- `.env` 为本地密钥文件，**未纳入版本控制**；参考 `.env.example` 自行创建
- 素材/输出目录（`02_BGM`、`03_粗剪输出`、`05_配音`、`shipin`）与数据库（`*.db`）未纳入
- 完整运行环境（含模型/素材）保存在本机：`E:\树剪整理\01_主程序源码\树剪软件相关文件\`

## 📜 版本历史

见 `CHANGELOG.md`（当前主版本 v13 安装于 `E:\树剪整理\02_安装程序\TreeCut_v13\`）
