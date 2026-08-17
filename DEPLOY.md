# 树剪 TreeCut v10.3 — 分发部署指南

## 方式一：源码分发（开发者）

```bash
# 1. 安装 Python 3.12
# 2. 克隆/复制项目到目标电脑
# 3. 安装依赖
pip install -r requirements.txt

# 4. 首次配置
python setup_wizard.py

# 5. 启动
python tree_cut_app.py
```

## 方式二：打包为独立 .exe

```bash
# 1. 在当前电脑打包
pip install pyinstaller
python build_exe.py

# 2. 输出文件
# dist/树剪TreeCut.exe  (约 800MB，包含 Python + 所有依赖)
```

将 `树剪TreeCut.exe` 连同以下文件一起分发：
- `.env.example` → 用户重命名为 `.env` 并填入自己的 API Key
- `protected_words.json` (行业词库)
- `tree_icon.ico` (图标)
- 【可选】`ai_material_library.db` (预建的素材索引库)
- 【可选】`02_BGM/` (预置背景音乐)

## 方式三：制作 Windows 安装包

```bash
# 1. 先完成方式二，得到 dist/树剪TreeCut.exe

# 2. 下载 Inno Setup 6
# https://jrsoftware.org/isinfo.php

# 3. 用 Inno Setup Compiler 打开 installer.iss
#    Build → Compile

# 4. 输出文件
# Output/树剪TreeCut_Setup_v10.3.exe
# 用户双击安装，自动创建桌面快捷方式、开始菜单
```

## 目标电脑要求

| 组件 | 最低配置 | 推荐配置 |
|------|----------|----------|
| 操作系统 | Windows 10/11 64位 | Windows 11 |
| 内存 | 8 GB | 16 GB |
| 磁盘 | 2 GB 空闲 | 5 GB（含素材库） |
| Python | 3.12（仅源码分发需要） | 3.12 |
| 网络 | 需要（DeepSeek API + Edge TTS） | — |

## 可选组件

| 组件 | 用途 | 安装方式 |
|------|------|----------|
| Ollama | 视觉画面分析 | `winget install Ollama.Ollama` |
| Qwen2.5-VL:7B | AI 识别岛台材质/风格 | `ollama pull qwen2.5vl:7b` |
| FFmpeg | 视频抽帧 | `winget install FFmpeg` |

## 用户首次运行步骤

1. 双击 `树剪TreeCut.exe`
2. 首次运行自动弹出配置向导（setup_wizard.py）
3. 填入 DeepSeek API Key
4. 设置素材路径（Z:\ 或自定义）
5. 设置输出路径
6. 保存后即可使用
