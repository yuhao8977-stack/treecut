"""
树剪 TreeCut v11.1 — 内置帮助文档窗口
================================================================
显示使用教程和快捷参考。
用法: from ui.help_window import show_help; show_help(parent)
"""
import tkinter as tk
from tkinter import ttk, scrolledtext
from pathlib import Path


HELP_CONTENT = """
树剪 TreeCut v11.1 — 使用教程
================================================================

一、快速开始
  1. 启动软件: 双击树剪.exe 或运行 python 树剪.py
  2. 输入关键词: 在「快速生成」页输入卖点关键词 (如"内嵌烤箱")
  3. 点击「生成视频草稿」: 等待 AI 完成文案→配音→匹配→草稿
  4. 在剪映中打开: 生成的草稿位于剪映草稿目录中

二、核心功能
  【快速生成】: 输入关键词 → 一键生成完整视频草稿
  【批量生产】: 粘贴多个脚本 → 批量生成视频 (支持 Excel 导入)
  【素材库】: 查看和管理所有素材文件
  【全盘检索】: 扫描本地磁盘找到视频素材
  【素材标注】: 关键帧 AI 识别 + 人工修正 → 反馈学习
  【脚本学习库】: 管理脚本 → 评分 → AI 风格分析
  【历史记录】: 查看已生成的草稿列表

三、AI 模型
  Qwen3-VL-4B: 视觉分析 (物体/材质/颜色/风格)
  SenseVoice: 情绪识别 (7种) + 事件检测 (6种)
  Whisper: 语音转文字 (large-v3)
  FAISS+BGE-M3: 向量语义检索

四、快捷键
  Ctrl+Enter: 快速生成
  Esc: 取消操作
  Ctrl+R: 刷新素材库

五、配置
  DeepSeek API Key: 系统设置 → AI模型配置
  素材路径: .env 文件中的 TREECUT_SELLING_DIR
  模型目录: models/ 文件夹

六、常见问题
  Q: 素材匹配不精准?
  A: 运行 python force_rebuild_faiss.py 重建索引

  Q: 视觉模型加载失败?
  A: 运行 dl_model.bat 下载模型 (~5.6GB)

  Q: 配音失败?
  A: 检查网络连接，Edge TTS 需要联网
"""


def show_help(parent=None):
    """显示帮助窗口"""
    win = tk.Toplevel(parent)
    win.title("树剪 TreeCut 使用教程")
    win.geometry("700x550")

    # 标题
    header = ttk.Label(win, text="树剪 TreeCut v11.1 — 使用教程",
                       font=("Microsoft YaHei", 14, "bold"))
    header.pack(pady=8)

    # 内容 (ScrolledText)
    text_area = scrolledtext.ScrolledText(
        win, wrap=tk.WORD,
        font=("Microsoft YaHei", 10),
        bg="#1a1a2e", fg="#e8eaf6",
        insertbackground="#fff",
    )
    text_area.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # 尝试读取外部帮助文件
    help_file = Path(__file__).parent.parent / "README.md"
    if help_file.exists():
        content = help_file.read_text(encoding="utf-8")
    elif (Path(__file__).parent.parent / "REFACTOR_COMPLETE.md").exists():
        content = (Path(__file__).parent.parent / "REFACTOR_COMPLETE.md").read_text(encoding="utf-8")
    else:
        content = HELP_CONTENT

    text_area.insert(tk.END, content)
    text_area.config(state=tk.DISABLED)

    # 关闭按钮
    ttk.Button(win, text="关闭", command=win.destroy).pack(pady=6)
