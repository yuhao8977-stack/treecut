#!/usr/bin/env python3
"""
树剪 TreeCut — 首次运行配置向导
引导用户完成: API Key、素材路径、BGM路径 等配置

用法:
  python setup_wizard.py          # 图形向导
  tree_cut_app.py --setup         # 从主程序触发
"""

import os, sys, json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

PROJECT_ROOT = Path(__file__).parent
ENV_FILE = PROJECT_ROOT / ".env"

# 导入核心配置的默认值（单一来源，避免与 config.py 重复）
try:
    from core.config import DEFAULTS as _cfg_defaults
    _D = lambda key, fb: _cfg_defaults.get(key, fb)
except Exception:
    _cfg_defaults = {}
    _D = lambda key, fb: fb

class SetupWizard:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("树剪 TreeCut — 首次配置向导")
        self.root.geometry("620x520")
        self.root.resizable(False, False)
        self._center_window()
        self._build_ui()
        self._load_existing()

    def _center_window(self):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = 620, 520
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//3}")

    def _load_existing(self):
        """加载已有的 .env 配置"""
        if ENV_FILE.exists():
            for line in ENV_FILE.read_text(encoding="utf-8").split("\n"):
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, val = line.split("=", 1)
                    key, val = key.strip(), val.strip().strip('"')
                    if key in self._entries:
                        self._entries[key].delete(0, "end")
                        self._entries[key].insert(0, val)

    def _build_ui(self):
        self._entries = {}
        frame = ttk.Frame(self.root, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="树剪 TreeCut v10.3", font=("Microsoft YaHei", 18, "bold")).pack(pady=(0, 5))
        ttk.Label(frame, text="首次使用前，请完成以下配置。留空则使用默认值。",
                  foreground="gray").pack(pady=(0, 15))

        notebook = ttk.Notebook(frame)
        notebook.pack(fill="both", expand=True)

        # === Tab 1: API Key ===
        t1 = ttk.Frame(notebook, padding=15)
        notebook.add(t1, text="API Key")

        self._add_field(t1, "DEEPSEEK_API_KEY", "DeepSeek API Key *",
                       "必填！用于 AI 生成文案。\n获取地址: https://platform.deepseek.com/api_keys", row=0, required=True)
        self._add_field(t1, "PIXABAY_API_KEY", "Pixabay API Key (可选)",
                       "用于自动下载免费背景音乐。\n获取地址: https://pixabay.com/api/docs/", row=1)

        # === Tab 2: 素材路径 ===
        t2 = ttk.Frame(notebook, padding=15)
        notebook.add(t2, text="素材路径")

        self._add_path_field(t2, "TREECUT_SELLING_DIR", "卖点展示类素材目录",
                            _D("TREECUT_SELLING_DIR", r"Z:\已处理素材\卖点展示类素材"), row=0)
        self._add_path_field(t2, "TREECUT_EFFECTS_DIR", "效果展示类素材目录",
                            _D("TREECUT_EFFECTS_DIR", r"Z:\已处理素材\效果展示类素材"), row=1)
        self._add_path_field(t2, "TREECUT_BGROUP_DIR", "B组补充素材目录",
                            _D("TREECUT_BGROUP_DIR", r"Z:\B组更新视频"), row=2)

        # === Tab 3: 输出路径 ===
        t3 = ttk.Frame(notebook, padding=15)
        notebook.add(t3, text="输出路径")

        self._add_path_field(t3, "TREECUT_DRAFT_DIR", "草稿输出目录",
                            _D("TREECUT_DRAFT_DIR", str(PROJECT_ROOT / "03_粗剪输出")), row=0)
        self._add_path_field(t3, "TREECUT_BGM_DIR", "BGM 音乐目录",
                            _D("TREECUT_BGM_DIR", str(PROJECT_ROOT / "02_BGM")), row=1)

        # === Tab 4: 高级 ===
        t4 = ttk.Frame(notebook, padding=15)
        notebook.add(t4, text="高级")

        self._add_field(t4, "TREECUT_WEB_PORT", "Web 控制台端口",
                       "Gradio Web UI 端口号。\n留空默认 7860。设 0 禁用 Web UI。", row=0)
        self._add_field(t4, "TREECUT_WEB_TOKEN", "Web 访问令牌",
                       "设置后 Web UI 需要密码访问。\n留空则不启用认证。", row=1)

        # === Tab 5: 视觉模型下载 ===
        t5 = ttk.Frame(notebook, padding=15); notebook.add(t5, text="视觉模型")
        ttk.Label(t5, text="AI 视觉模型下载", font=("Microsoft YaHei", 13, "bold")).pack(anchor="w", pady=5)
        self.model_var = tk.StringVar(value=_D("TREECUT_VISION_MODEL", "qwen2.5-ollama"))
        for label, key in [("Qwen2.5-VL (Ollama,默认)","qwen2.5-ollama"),("Qwen3-VL-7B (14GB,推荐)","qwen3-7b"),("Qwen3-VL-3B (6GB)","qwen3-3b"),("Kimi-VL (6GB)","kimi-vl"),("Tarsier2 (14GB)","tarsier2"),("Florence-2 (0.5GB)","florence2")]:
            ttk.Radiobutton(t5, text=label, variable=self.model_var, value=key).pack(anchor="w", pady=2)
        self.model_status = ttk.Label(t5, text="", foreground="gray"); self.model_status.pack(pady=5)
        ttk.Button(t5, text="检查状态", command=self._check_models).pack(side="left", padx=4)
        ttk.Button(t5, text="下载", command=self._download_model).pack(side="left", padx=4)

        # === 按钮 ===
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=(15, 0))
        ttk.Button(btn_frame, text="保存配置 / Save Config",
                  command=self._save).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="跳过 / Skip",
                  command=self.root.destroy).pack(side="right", padx=4)

    def _add_field(self, parent, key, label, help_text, row, required=False):
        display_label = label + (" *必填" if required else "")
        ttk.Label(parent, text=display_label,
                 font=("Microsoft YaHei", 12),
                 foreground="red" if required else "black").grid(row=row, column=0, sticky="w", pady=5)
        entry = ttk.Entry(parent, width=55)
        entry.grid(row=row+1, column=0, sticky="ew", pady=2)
        ttk.Label(parent, text=help_text, foreground="gray", font=("Microsoft YaHei", 9)
                 ).grid(row=row+2, column=0, sticky="w", pady=(0, 10))
        self._entries[key] = entry

    def _add_path_field(self, parent, key, label, default, row):
        ttk.Label(parent, text=label, font=("Microsoft YaHei", 12)
                 ).grid(row=row, column=0, sticky="w", pady=(10, 2))
        entry_frame = ttk.Frame(parent)
        entry_frame.grid(row=row+1, column=0, sticky="ew", pady=2)
        entry = ttk.Entry(entry_frame, width=42)
        entry.pack(side="left", fill="x", expand=True)
        entry.insert(0, default)
        def _browse():
            path = filedialog.askdirectory(title=f"选择: {label}")
            if path: entry.delete(0, "end"); entry.insert(0, path)
        ttk.Button(entry_frame, text="浏览...", command=_browse).pack(side="left", padx=4)
        self._entries[key] = entry

    def _save(self):
        """保存 .env 文件"""
        # 检查必填
        deepseek_key = self._entries.get("DEEPSEEK_API_KEY")
        if deepseek_key:
            val = deepseek_key.get().strip()
            if not val or val == "your_deepseek_api_key_here":
                messagebox.showwarning("必填字段", "请填写 DeepSeek API Key！\nAI 文案生成功能依赖此项。")
                return

        lines = ["# 树剪 TreeCut v10.3 配置文件", f"# 生成时间: {__import__('datetime').datetime.now().isoformat()[:19]}", ""]
        for key, entry in self._entries.items():
            val = entry.get().strip()
            if val:
                lines.append(f"{key}={val}")
            else:
                lines.append(f"# {key}=")

        ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # 创建必要的目录
        for key in ["TREECUT_DRAFT_DIR", "TREECUT_BGM_DIR"]:
            if key in self._entries:
                val = self._entries[key].get().strip()
                if val:
                    Path(val).mkdir(parents=True, exist_ok=True)

        messagebox.showinfo("配置完成",
            "配置已保存！\n\n"
            "接下来:\n"
            "1. 确保素材路径 (Z:盘) 可访问\n"
            "2. (可选) 安装 Ollama 并下载 Qwen2.5-VL 模型\n"
            "   用于视觉画面分析\n"
            "3. 启动桌面应用开始使用！")
        self.root.destroy()

    def _check_models(self):
        try:
            from utils.model_downloader import ensure_model_available
            k = self.model_var.get(); ok = ensure_model_available(k)
            self.model_status.config(text=f"{'✅ 已缓存' if ok else '❌ 需下载'} — {k}", foreground="#4caf50" if ok else "#f44336")
        except Exception as e: self.model_status.config(text=f"错误: {e}")

    def _download_model(self):
        k = self.model_var.get(); self.model_status.config(text="下载中..."); self.root.update()
        def _dl():
            from utils.model_downloader import download_model
            ok = download_model(k)
            self.root.after(0, lambda: self.model_status.config(text=f"{'✅ 完成' if ok else '❌ 失败'} — {k}"))
        import threading; threading.Thread(target=_dl, daemon=True).start()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    SetupWizard().run()
