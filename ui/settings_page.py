"""
树剪 — 统一设置页面 v11.1
动态模型权重 + DeepSeek AI 助手 + 延迟加载优化
"""
import os, sys, json, time, threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from ui.rounded_button import RoundedButton

# ttkbootstrap 可选导入
try:
    import ttkbootstrap as tb
    _HAS_BOOTSTRAP = True
except ImportError:
    _HAS_BOOTSTRAP = False


class SettingsPage:
    """统一设置页面 — 独立窗口 (v11.1 延迟加载)"""

    def __init__(self, app):
        self.app = app
        self.top = tk.Toplevel(app.root)
        self.top.title("系统设置 / Settings — 树剪 TreeCut v11.1")
        self.top.geometry("780x720")
        self.top.resizable(True, True)
        self.top.minsize(650, 580)
        self._center_window()

        # 延迟加载追踪
        self._tab_built = {}
        self._tab_loading = {}

        self._build()

    def _center_window(self):
        self.top.update_idletasks()
        sw = self.top.winfo_screenwidth()
        sh = self.top.winfo_screenheight()
        w, h = 780, 720
        self.top.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-620)//3}")

    # ════════════════════════════════════════════════
    # 主框架 — 延迟加载
    # ════════════════════════════════════════════════

    def _build(self):
        """只创建 Notebook 框架，标签页内容延迟构建"""
        self.nb = ttk.Notebook(self.top)
        self.nb.pack(fill="both", expand=True, padx=6, pady=6)

        # 预建两个标签页的占位 frame（不填充内容）
        self._tab_ai_placeholder = ttk.Frame(self.nb, padding=15)
        self.nb.add(self._tab_ai_placeholder, text="AI模型配置")

        self._tab_chat_placeholder = ttk.Frame(self.nb, padding=15)
        self.nb.add(self._tab_chat_placeholder, text="AI 助手")

        # 只在用户切换标签页时才构建内容
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # 立即构建第一个（默认选中的）标签页
        self.top.after(10, self._ensure_tab_built)

    def _on_tab_changed(self, event=None):
        """标签页切换时，延迟构建目标标签页"""
        self.top.after(10, self._ensure_tab_built)

    def _ensure_tab_built(self):
        """确保当前标签页已构建"""
        try:
            idx = self.nb.index(self.nb.select())
            tab_name = self.nb.tab(idx, "text")
        except Exception:
            return

        if tab_name == "AI模型配置" and not self._tab_built.get("ai"):
            self._tab_built["ai"] = True
            self._build_ai_tab_content()
        elif tab_name == "AI 助手" and not self._tab_built.get("chat"):
            self._tab_built["chat"] = True
            self._build_chat_tab_content()

    # ════════════════════════════════════════════════
    # Tab 1: AI 模型配置 (在后台线程检测模型)
    # ════════════════════════════════════════════════

    def _build_ai_tab_content(self):
        """在占位 frame 中构建 AI 配置标签页的全部内容"""
        tab = self._tab_ai_placeholder

        # ── DeepSeek API ──
        ds_frame = ttk.LabelFrame(tab, text="DeepSeek API 配置", padding=10)
        ds_frame.pack(fill="x", pady=5)

        ttk.Label(ds_frame, text="API Key:").grid(row=0, column=0, sticky="w")
        _existing_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not _existing_key:
            try:
                from utils.security import safe_read_env
                _env = safe_read_env(Path(__file__).parent.parent / ".env")
                _existing_key = _env.get("DEEPSEEK_API_KEY", "")
            except Exception:
                _existing_key = ""
        self.ds_key_var = tk.StringVar(value=_existing_key)
        tk.Entry(ds_frame, textvariable=self.ds_key_var, width=45, show="*").grid(
            row=0, column=1, padx=5)

        ttk.Label(ds_frame, text="模型:").grid(row=1, column=0, sticky="w", pady=5)
        self.ds_model_var = tk.StringVar(value="deepseek-chat")
        ttk.Combobox(ds_frame, textvariable=self.ds_model_var,
                     values=["deepseek-chat", "deepseek-coder"], width=18).grid(
            row=1, column=1, padx=5, sticky="w")

        ds_btn = ttk.Frame(ds_frame)
        ds_btn.grid(row=2, column=0, columnspan=2, pady=8)
        RoundedButton(ds_btn, text="测试连接", command=self._test_deepseek, width=100, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="left", padx=4)
        RoundedButton(ds_btn, text="保存配置", command=self._save_ds_config, width=100, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="left", padx=4)
        self.ds_status = ttk.Label(ds_btn, text="", foreground="#4a7c4f")
        self.ds_status.pack(side="left", padx=12)

        # ── 动态模型权重 ──
        w_frame = ttk.LabelFrame(tab, text="模型融合权重配置 (动态识别)", padding=10)
        w_frame.pack(fill="x", pady=8)

        self.weight_vars = {}
        self.model_info_labels = {}

        # 控制栏
        ctrl = ttk.Frame(w_frame)
        ctrl.pack(fill="x", pady=(0, 6))
        RoundedButton(ctrl, text="刷新模型列表", command=self._refresh_model_list_async
, width=100, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="left", padx=2)
        self.w_refresh_status = ttk.Label(ctrl, text="正在检测模型...", foreground="#ffb74d")
        self.w_refresh_status.pack(side="left", padx=10)

        # 权重容器
        self.weights_container = ttk.Frame(w_frame)
        self.weights_container.pack(fill="x")

        # 初始显示 loading
        ttk.Label(self.weights_container, text="检测中，请稍候...",
                  foreground="#4a7c4f").pack(pady=10)

        # 保存按钮
        btn_row = ttk.Frame(w_frame)
        btn_row.pack(fill="x", pady=(8, 0))
        self.weight_auto_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(btn_row, text="DeepSeek自动调整权重",
                        variable=self.weight_auto_var).pack(side="left")
        RoundedButton(btn_row, text="保存权重配置", command=self._save_weights
, width=100, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="right", padx=4)

        # ── 后台线程加载模型列表 ──
        threading.Thread(target=self._load_models_bg, daemon=True).start()

    def _load_models_bg(self):
        """后台加载模型列表，完成后再更新 UI"""
        try:
            from core.config import get_active_models_info
            models = get_active_models_info()
        except Exception as e:
            models = []
            err = str(e)[:80]
        else:
            err = None

        def _update():
            if err:
                self.w_refresh_status.config(
                    text=f"获取失败: {err}", foreground="#e53935")
                return
            self._populate_model_rows(models)
            self.w_refresh_status.config(
                text=f"识别到 {len(models)} 个模型 ({sum(1 for m in models if m['enabled'])} 个可用)",
                foreground="#43a047")
        self.top.after(0, _update)

    def _populate_model_rows(self, models):
        """用模型数据填充 UI（必须在主线程调用）"""
        for w in self.weights_container.winfo_children():
            w.destroy()
        self.weight_vars.clear()
        self.model_info_labels.clear()

        if not models:
            ttk.Label(self.weights_container, text="未检测到模型",
                      foreground="#e53935").pack(pady=10)
            return

        # 表头
        hdr = ttk.Frame(self.weights_container)
        hdr.pack(fill="x", pady=2)
        ttk.Label(hdr, text="模型", font=("", 9, "bold"), width=22).pack(side="left")
        ttk.Label(hdr, text="权重", font=("", 9, "bold"), width=8).pack(side="left")
        ttk.Label(hdr, text="状态", font=("", 9, "bold"), width=10).pack(side="left")
        ttk.Label(hdr, text="说明", font=("", 9)).pack(side="left", fill="x", expand=True)

        for m in models:
            row = ttk.Frame(self.weights_container)
            row.pack(fill="x", pady=1)

            # 名字
            ttk.Label(row, text=m["name"][:22], width=22, anchor="w").pack(
                side="left", padx=(0, 4))

            # 权重
            var = tk.DoubleVar(value=m["weight"])
            scale = ttk.Scale(row, from_=0.0, to=0.60, variable=var,
                              length=120, orient="horizontal")
            scale.pack(side="left", padx=2)
            val_label = ttk.Label(row, text=f"{m['weight']:.2f}", width=5)
            val_label.pack(side="left", padx=2)
            scale.configure(command=lambda v, l=val_label: l.config(text=f"{float(v):.2f}"))

            # 状态
            ok = m["enabled"]
            ttk.Label(row, text="[OK]" if ok else "[OFF]", width=7,
                      foreground="#43a047" if ok else "#e53935").pack(side="left", padx=2)

            # 说明
            ttk.Label(row, text=m.get("description", "")[:45],
                      foreground="#4a7c4f").pack(side="left", padx=4)

            self.weight_vars[m["name"]] = var
            self.model_info_labels[m["name"]] = {
                "var": var, "label": val_label, "type": m["type"], "enabled": ok,
            }

    def _refresh_model_list_async(self):
        """用户点击刷新"""
        self.w_refresh_status.config(text="正在检测模型...", foreground="#ffb74d")
        # 清空旧内容
        for w in self.weights_container.winfo_children():
            w.destroy()
        ttk.Label(self.weights_container, text="检测中，请稍候...",
                  foreground="#4a7c4f").pack(pady=10)
        threading.Thread(target=self._load_models_bg, daemon=True).start()

    def _save_weights(self):
        weights = {}
        for name, var in self.weight_vars.items():
            weights[name] = round(var.get(), 3)

        if not weights:
            messagebox.showwarning("提示", "没有可保存的权重")
            return

        config_path = Path(__file__).parent.parent / "AI素材库" / "model_weights.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps({
            "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "weights": weights,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        # 类型→权重映射
        type_weights = {}
        for name, info in self.model_info_labels.items():
            type_weights[info["type"]] = round(info["var"].get(), 3)

        # 更新 MODULE_WEIGHTS
        try:
            from core import config
            config.MODEL_WEIGHTS = type_weights
        except Exception:
            pass

        # 应用到 TagMerger
        try:
            from core.tag_merger import TagMerger
            tm = TagMerger()
            type_map = {
                "vision": "qwen_vl", "audio_emotion": "clip",
                "audio_transcribe": "whisper", "knowledge": "filename",
                "retrieval": "yolo",
            }
            for ut, ik in type_map.items():
                if ut in type_weights:
                    tm._weights[ik] = type_weights[ut]
        except Exception:
            pass

        messagebox.showinfo("保存成功",
            f"已保存 {len(weights)} 个模型权重:\n\n" +
            "\n".join(f"  {k}: {v:.3f}" for k, v in list(weights.items())[:10]))

    def _test_deepseek(self):
        key = self.ds_key_var.get().strip()
        if not key:
            messagebox.showwarning("提示", "请先输入API Key")
            return
        self.ds_status.config(text="测试中...", foreground="#ffb74d")
        def _t():
            try:
                from core.deepseek_client import DeepSeekClient
                ds = DeepSeekClient(api_key=key, model=self.ds_model_var.get())
                ok, msg = ds.test_connection()
                self.top.after(0, lambda o=ok, m=msg: self.ds_status.config(
                    text=m[:60], foreground="#43a047" if o else "#e53935"))
            except Exception as e:
                self.top.after(0, lambda e=e: self.ds_status.config(
                    text=str(e)[:60], foreground="#e53935"))
        threading.Thread(target=_t, daemon=True).start()

    def _save_ds_config(self):
        key = self.ds_key_var.get().strip()
        if key:
            os.environ["DEEPSEEK_API_KEY"] = key
            env_file = Path(__file__).parent.parent / ".env"
            lines = []
            if env_file.exists():
                lines = env_file.read_text(encoding="utf-8").splitlines()
            lines = [l for l in lines if not l.startswith("DEEPSEEK_API_KEY=")]
            lines.append(f"DEEPSEEK_API_KEY={key}")
            env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        messagebox.showinfo("保存", "DeepSeek配置已保存并生效")

    # ════════════════════════════════════════════════
    # Tab 2: DeepSeek AI 对话助手
    # ════════════════════════════════════════════════

    def _build_chat_tab_content(self):
        """在占位 frame 中构建 AI 助手标签页内容"""
        tab = self._tab_chat_placeholder

        # 标题
        ttk.Label(tab, text="[AI] DeepSeek 对话助手",
                  font=("Microsoft YaHei", 12, "bold")).pack(anchor="w", pady=(0, 6))

        # 快捷提问
        qf = ttk.Frame(tab)
        qf.pack(fill="x", pady=3)
        quick = [
            ("优化文案", "如何让生成的视频文案更有小红书爆款风格？"),
            ("素材库优化", "素材库标签覆盖率低，该怎么优化？"),
            ("参数调整", "视频规格1080x1920，怎样调整能让效果更好？"),
            ("故障排查", "配音生成失败是什么原因？"),
            ("匹配优化", "如何让画面匹配更精准？"),
        ]
        for label, question in quick:
            RoundedButton(qf, text=label,
                           width=100, height=34, bg_color="#e0e0e0", fg_color="#212529",
                           hover_color="#d0e0ff", radius=10,
                           command=lambda q=question: self._fill_question(q)
                           ).pack(side="left", padx=2)

        # 输入区
        input_frame = ttk.Frame(tab)
        input_frame.pack(fill="x", pady=4)

        self.ai_input = tk.Text(input_frame, font=("Microsoft YaHei", 11),
                                bg="#ffffff", fg="#1b5e20", insertbackground="#1b5e20")
        self.ai_input.pack(side="left", fill="both", expand=True)

        # ── 发送按钮 (放在输入框右侧，大而明显) ──
        btn_col = ttk.Frame(input_frame)
        btn_col.pack(side="right", padx=(8, 0), fill="y")

        # 圆角发送按钮
        self.send_btn = RoundedButton(
            btn_col,
            text="发送 / Send",
            font=("Microsoft YaHei", 11, "bold"),
            width=80, height=38,
            bg_color="#0d6efd", fg_color="#ffffff", hover_color="#0b5ed7", radius=12,
            command=self._ask_ai,
        )
        self.send_btn.pack(pady=2, fill="y")

        RoundedButton(
            btn_col, text="清空", font=("Microsoft YaHei", 9),
            width=60, height=32,
            bg_color="#4a7c4f", fg_color="#ffffff", hover_color="#6d9b6f", radius=10,
            command=lambda: self.ai_input.delete("1.0", "end")
        ).pack(pady=2)

        # 也绑定 Ctrl+Enter 快捷键
        self.ai_input.bind("<Control-Return>", lambda e: self._ask_ai())
        self.ai_input.bind("<Control-KeyPress-Return>", lambda e: self._ask_ai())

        # 状态栏
        st_frame = ttk.Frame(tab)
        st_frame.pack(fill="x", pady=(4, 0))
        self.ai_status = ttk.Label(st_frame, text="就绪 — 输入问题后点击「发送」",
                                   foreground="#4a7c4f")
        self.ai_status.pack(side="left", padx=2)
        RoundedButton(st_frame, text="清空对话", command=self._clear_chat
, width=100, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="right", padx=2)

        # 对话显示区
        self.ai_output = scrolledtext.ScrolledText(
            tab, font=("Microsoft YaHei", 10),
            bg="#e8f5e9", fg="#1b5e20",
            state="disabled", wrap="word",
        )
        self.ai_output.pack(fill="both", expand=True, pady=4)

        self._chat_history = []

        # 初始化提示
        self._append_chat("系统",
            "欢迎使用树剪 AI 助手！\n"
            "输入问题后点击右侧「发送」按钮或按 Ctrl+Enter 发送。\n"
            "示例: 「如何让画面匹配更精准？」",
            "#888")

    def _fill_question(self, q):
        self.ai_input.delete("1.0", "end")
        self.ai_input.insert("1.0", q)

    def _clear_chat(self):
        self.ai_output.config(state="normal")
        self.ai_output.delete("1.0", "end")
        self.ai_output.config(state="disabled")
        self._chat_history = []

    def _append_chat(self, role, text, color):
        self.ai_output.config(state="normal")
        ts = time.strftime("%H:%M:%S")
        self.ai_output.insert("end", f"{ts} [{role}]\n", ("ts",))
        self.ai_output.insert("end", text + "\n\n")
        self.ai_output.tag_config("ts", foreground="#81c784")
        self.ai_output.see("end")
        self.ai_output.config(state="disabled")
        self._chat_history.append({"role": role, "text": text, "time": ts})

    def _ask_ai(self):
        q = self.ai_input.get("1.0", "end-1c").strip()
        if not q:
            messagebox.showinfo("提示", "请输入问题后再点击发送")
            return

        # 检查 API Key
        key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not key:
            try:
                from utils.security import safe_read_env
                key = safe_read_env(Path(__file__).parent.parent / ".env").get(
                    "DEEPSEEK_API_KEY", "")
            except Exception:
                pass
        if not key:
            self._append_chat("系统",
                "请先在「AI模型配置」页面设置 DeepSeek API Key，然后重新提问。",
                "#e53935")
            self.ai_status.config(text="API Key 未配置", foreground="#e53935")
            return

        # 显示用户消息
        self._append_chat("你", q, "#2e7d32")
        self.ai_status.config(text="思考中...", foreground="#ffb74d")
        self.send_btn.config(state="disabled", text="等待中...")

        def _call():
            try:
                from core.deepseek_client import DeepSeekClient
                ds = DeepSeekClient()
                if not ds.available:
                    self.top.after(0, lambda: (
                        self._append_chat("AI",
                            "API Key 无效或 openai 未安装。请在 AI模型配置 页面检查配置。",
                            "#e53935"),
                        self.ai_status.config(text="API Key 无效", foreground="#e53935"),
                        self.send_btn.config(state="normal", text="发送 / Send"),
                    ))
                    return

                sys_prompt = (
                    "你是树剪TreeCut v11.1的AI助手。树剪是一个岛台品牌AI视频半自动剪辑工具。"
                    "核心模型: Qwen3-VL-4B(视觉分析)、SenseVoice(情绪识别)、"
                    "Whisper(语音转写)、FAISS+BGE-M3(向量检索)。"
                    "功能: AI文案生成、AI配音、视觉分析、语音识别、行业知识库、剪映草稿生成。"
                    "帮助用户优化视频生成、解决软件问题、提供家居家装行业建议。回答简洁专业。"
                )
                answer = ds._call(sys_prompt, q, max_tokens=800)

                def _done(a=answer):
                    if a:
                        self._append_chat("AI", a, "#43a047")
                        self.ai_status.config(text="就绪", foreground="#43a047")
                    else:
                        self._append_chat("AI",
                            "API 返回空结果，请检查网络或 API Key 是否有效。",
                            "#e53935")
                        self.ai_status.config(text="调用失败", foreground="#e53935")
                    self.send_btn.config(state="normal", text="发送 / Send")

                self.top.after(0, _done)

            except Exception as e:
                def _err():
                    self._append_chat("AI", f"调用出错: {str(e)[:300]}", "#e53935")
                    self.ai_status.config(text="出错", foreground="#e53935")
                    self.send_btn.config(state="normal", text="发送 / Send")
                self.top.after(0, _err)

        threading.Thread(target=_call, daemon=True).start()
