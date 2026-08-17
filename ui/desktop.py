#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
树剪 TreeCut v11.1 - 完整功能桌面应用 (ttkbootstrap浅色主题)
保留全部7个Tab + 菜单 + 进度 + 快捷键
"""
import sys, os, json, time, threading
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext
import ttkbootstrap as tb
from ui.rounded_button import RoundedButton


# ── 线程安全全局变量 ──
_ve = None; _ve_lock = threading.Lock()
_folder_cache = None; _cache_lock = threading.Lock()
_ui_state_lock = threading.Lock()  # UI状态锁 — 保护 _folder_ui_built 等

def format_count(n):
    if n >= 100000: return f"{n/10000:.1f}w"
    if n >= 1000: return f"{n/1000:.1f}k"
    return str(n)

def _get_ve():
    global _ve
    if _ve is None:
        with _ve_lock:
            if _ve is None: import core as _ve
    return _ve

def _get_folders_fast():
    global _folder_cache
    with _cache_lock:
        if _folder_cache is not None: return _folder_cache
    cf = Path(__file__).parent.parent / "folder_cache.json"
    try:
        if cf.exists():
            data = json.loads(cf.read_text(encoding="utf-8"))
            if time.time() - data.get("ts",0) < 86400:
                _folder_cache = data.get("folders",[])
                if _folder_cache: return _folder_cache
    except json.JSONDecodeError:
        cf.unlink(missing_ok=True)
        print("   [Cache] 缓存文件损坏，已删除并重建")
    except Exception as _e:
        from utils.logging import log_warning
        log_warning('desktop', str(_e)[:80])
    try:
        import sqlite3
        db = Path(__file__).parent.parent / "ai_material_library.db"
        if db.exists():
            conn = sqlite3.connect(str(db))
            rows = conn.execute("SELECT source_folder, COUNT(*) as cnt FROM materials WHERE source_folder != '' GROUP BY source_folder ORDER BY cnt DESC").fetchall()
            conn.close()
            _folder_cache = [{"name":r[0],"count":r[1]} for r in rows if r[0].strip()]
            if _folder_cache: return _folder_cache
    except Exception as _e: from utils.logging import log_warning; log_warning('desktop', str(_e)[:80])
    _folder_cache = []
    for sp in [os.environ.get("TREECUT_SELLING_DIR", r"Z:\已处理素材\卖点展示类素材"),
               os.environ.get("TREECUT_EFFECTS_DIR", r"Z:\已处理素材\效果展示类素材"),
               os.environ.get("TREECUT_BGROUP_DIR", r"Z:\B组更新视频")]:
        p = Path(sp)
        if p.exists():
            for d in sorted(p.iterdir()):
                if d.is_dir():
                    try: cnt = len(list(d.rglob("*.mp4")))
                    except Exception: cnt = 0
                    if cnt > 0: _folder_cache.append({"name":d.name,"count":cnt})
    _folder_cache.sort(key=lambda x:-x["count"])
    try: cf.write_text(json.dumps({"ts":time.time(),"folders":_folder_cache},ensure_ascii=False),encoding="utf-8")
    except Exception as _e: from utils.logging import log_warning; log_warning('desktop', str(_e)[:80])
    return _folder_cache

class TreeCutApp:
    def __init__(self):
        self.root = tb.Window(themename="litera")
        self.root.title("树剪 TreeCut v11.1")
        sw = self.root.winfo_screenwidth(); sh = self.root.winfo_screenheight()
        w = min(1100, int(sw*0.75)); h = min(800, int(sh*0.85))
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//3}")
        self.root.minsize(400, 400)

        # ── Notebook tab styling (green) ──
        try:
            tb.Style().configure("TNotebook.Tab", background="#2e7d32", foreground="white",
                                padding=[14, 5], font=("Microsoft YaHei", 10, "bold"))
            tb.Style().map("TNotebook.Tab",
                      background=[("selected", "#1b5e20"), ("active", "#43a047")],
                      foreground=[("selected", "white"), ("active", "white")])
        except Exception:
            pass  # ttkbootstrap may override custom TNotebook styling

        # ── Background deeper green ──
        self.root.configure(bg="#c8e6c9")

        self._generating = False
        self._cancel_event = threading.Event()
        self._ve_ready = False; self._cache_ready = False
        self._folder_ui_built = False; self.folder_panel_visible = False
        self._gen_folder_visible = False; self._gen_folder_check_vars = {}
        self.folder_check_vars = {}; self.batch_folder_visible = False; self.batch_folder_vars = {}

        self.recent_kw = self._load_json("recent_kw.json", [])

        try:
            ico = Path(__file__).parent.parent / "tree_icon.ico"
            if ico.exists(): self.root.iconbitmap(str(ico))
        except Exception as _e: from utils.logging import log_warning; log_warning('desktop', str(_e)[:80])

        self._build_menu()
        self._build_notebook()

        self.status_var = tk.StringVar(value="● 就绪 Ready")
        self.status_bar = tb.Label(self.root, textvariable=self.status_var,
                                    anchor="w", padding=6, background="#c8e6c9", foreground="#1b5e20")
        self.status_bar.pack(side="bottom", fill="x")

        # 设置菜单栏颜色
        self.root.option_add('*TMenu*background', '#c8e6c9')
        self.root.option_add('*TMenu*foreground', '#1b5e20')

        self.root.bind('<Control-Return>', lambda e: self._on_generate())
        self.root.bind('<Escape>', lambda e: self._on_cancel())
        self.root.bind('<Control-r>', lambda e: self._on_refresh_lib())

        threading.Thread(target=self._warmup, daemon=True).start()

    def _set_status(self, msg): self.status_var.set(msg)
    def _load_json(self, fn, default):
        p = Path(__file__).parent / fn
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default
    def _save_json(self, fn, data):
        (Path(__file__).parent / fn).write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")

    # ═══════════════════ 菜单 ═══════════════════
    def _build_menu(self):
        mb = tk.Menu(self.root, bg="#c8e6c9", fg="#1b5e20",
                     activebackground="#a5d6a7", activeforeground="#1b5e20")
        self.root.config(menu=mb)
        tools = tk.Menu(mb, tearoff=0); mb.add_cascade(label="工具 / Tools", menu=tools)
        tools.add_command(label="系统状态 / Status", command=self._on_system_status)
        tools.add_command(label="交叉复查 / Review", command=self._on_review)
        tools.add_command(label="全盘素材扫描 / Scan All Videos", command=self._on_scan_all)
        tools.add_separator()
        tools.add_command(label="清除缓存 / Clear Cache", command=self._on_clear_all_cache)
        tools.add_command(label="系统设置 / Settings", command=self._on_settings)

        help_m = tk.Menu(mb, tearoff=0); mb.add_cascade(label="帮助 / Help", menu=help_m)
        help_m.add_command(label="使用教程 / Tutorial", command=lambda: self._show_help())
        help_m.add_command(label="关于 / About", command=lambda: messagebox.showinfo("关于","树剪 TreeCut v11.1\nAI视频半自动剪辑工具"))

    # ═══════════════════ 标签页 ═══════════════════
    def _build_notebook(self):
        self.nb = tb.Notebook(self.root, bootstyle="light")
        self.nb.pack(fill="both", expand=True, padx=6, pady=6)
        self._build_generate()
        self._build_material_panel()
        self._build_script_lib()
        self._build_history()
        self._build_review_tab()    # ★ v12.0: 審核面板
        self._build_logs_tab()      # ★ v12.0: 統一日志窗口
        self.nb.bind("<<NotebookTabChanged>>", self._on_nb_tab_change)

        # ★ v12.0: EventBus 訂閱 — 連接後台事件到UI
        self._subscribe_events()

    
    # ═══════════════ TAB 1: 生成 / Generate (单次+批量合并) ═══════════════
    def _build_generate(self):
        t = tb.Frame(self.nb, padding=10); self.nb.add(t, text="生成 / Generate")

        # ── 模式切换 ──
        mode_frame = tb.Labelframe(t, text="生成模式", padding=6)
        mode_frame.pack(fill="x", pady=(0,6))
        self.gen_mode = tk.StringVar(value="single")
        tb.Radiobutton(mode_frame, text="单次生成 (输入关键词, AI自动生成)", variable=self.gen_mode, value="single",
                       command=self._on_mode_change).pack(side="left", padx=10)
        tb.Radiobutton(mode_frame, text="批量生成 (粘贴多个脚本, 一次生成多条视频)", variable=self.gen_mode, value="batch",
                       command=self._on_mode_change).pack(side="left", padx=10)

        # ── 主内容区（左右分栏+可滚动）──
        main_frame = tb.Frame(t)
        main_frame.pack(fill="both", expand=True)
        # 左侧可滚动
        left_outer = tb.Frame(main_frame)
        left_outer.pack(side="left", fill="both", expand=True, padx=(0,6))
        canvas = tk.Canvas(left_outer, highlightthickness=0, bg="#c8e6c9")
        scrollbar = tb.Scrollbar(left_outer, orient="vertical", command=canvas.yview, bootstyle="round")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.left_panel = tb.Frame(canvas, padding=4)
        cw = canvas.create_window((0,0), window=self.left_panel, anchor="nw")
        self.left_panel.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cw, width=e.width))
        def _g_mw(e): canvas.yview_scroll(int(-1*(e.delta/120)),"units")
        canvas.bind("<MouseWheel>",_g_mw); self.left_panel.bind("<MouseWheel>",_g_mw)
        # 右侧日志 (固定宽度 340px)
        right_panel = tb.Frame(main_frame, width=340)
        right_panel.pack(side="right", fill="y", padx=(6,0))
        right_panel.pack_propagate(False)
        lf = tb.Labelframe(right_panel, text="日志 / Log")
        lf.pack(fill="both", expand=True)
        self.log_area = scrolledtext.ScrolledText(lf, font=("Consolas",10), bg="#c8e6c9", fg="#1b5e20")
        self.log_area.pack(fill="both", expand=True, padx=6, pady=6)

        # ═══════ 单次模式控件 ═══════
        self._single_frame = tb.Frame(self.left_panel)
        tb.Label(self._single_frame, text="关键词 / Keyword:", font=("Microsoft YaHei",11,"bold")).pack(anchor="w")
        presets = ["产品混剪","产品介绍","入户产品介绍","工厂产品介绍","产品工艺介绍",
                   "岩板台面耐造","内嵌烤箱","轨道插座","灯带","伸缩功能",
                   "海棠角","拉篮","连纹","圆弧设计","意式中古风","奶油风岛台"]
        all_kw = list(dict.fromkeys(presets + self.recent_kw))
        self.kw_entry = tb.Combobox(self._single_frame, values=all_kw, font=("Microsoft YaHei",12))
        self.kw_entry.pack(fill="x", pady=4); self.kw_entry.set("岩板台面耐造")
        tb.Label(self._single_frame, text="文案(可选) / Copy:", font=("Microsoft YaHei",11,"bold")).pack(anchor="w",pady=(8,0))
        self.copy_text = tb.Text(self._single_frame, height=4, font=("Microsoft YaHei",11))
        self.copy_text.pack(fill="x", pady=4)

        # ═══════ 批量模式控件 ═══════
        self._batch_frame = tb.Frame(self.left_panel)
        tb.Label(self._batch_frame, text="从Excel粘贴脚本 (自动识别):", font=("",11,"bold")).pack(anchor="w")
        self.batch_text = tb.Text(self._batch_frame, height=6, font=("Microsoft YaHei",11))
        self.batch_text.pack(fill="x", pady=4)

        bf = tb.Frame(self._batch_frame); bf.pack(fill="x", pady=4)
        RoundedButton(bf, text="识别并填充 / Auto-Fill", command=self._auto_fill_batch, width=150, height=36, bg_color="#0d6efd", fg_color="#ffffff", hover_color="#0b5ed7", radius=10).pack(side="left", padx=3)
        RoundedButton(bf, text="直接生成 / Generate", command=self._batch_gen, width=150, height=36, bg_color="#0d6efd", fg_color="#ffffff", hover_color="#0b5ed7", radius=10).pack(side="left", padx=3)
        RoundedButton(bf, text="清空", command=lambda: (self.batch_text.delete("1.0","end"),self._set_status("已清空")), width=90).pack(side="left", padx=3)
        self.batch_force_line = tk.BooleanVar(value=False)
        tb.Checkbutton(bf, text="强制按行", variable=self.batch_force_line).pack(side="left", padx=6)

        tb.Label(self._batch_frame, text="或逐条输入 / Or enter manually:").pack(anchor="w", pady=(8,0))
        sc = tb.Frame(self._batch_frame); sc.pack(fill="x")
        self.batch_slot_count = tk.IntVar(value=3)
        for v in [2,3,4,5,10,15,20,30]: tb.Radiobutton(sc, text=str(v), variable=self.batch_slot_count, value=v).pack(side="left", padx=3)
        RoundedButton(sc, text="生成输入框", command=self._build_slots, width=100, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="left", padx=6)
        self.slots_frame = tb.Frame(self._batch_frame); self.slots_frame.pack(fill="x", pady=4)
        self.script_slots = []

        # 批量结果表格
        btbl = tb.Frame(self._batch_frame); btbl.pack(fill="x")
        self.batch_tree = tb.Treeview(btbl, columns=("#","status","preview"), show="headings", height=8)
        self.batch_tree.heading("#", text="#"); self.batch_tree.column("#", width=50)
        self.batch_tree.heading("status", text="状态"); self.batch_tree.column("status", width=100)
        self.batch_tree.heading("preview", text="预览"); self.batch_tree.column("preview", width=350)
        self.batch_tree.pack(fill="x")

        self.batch_prog = tb.Progressbar(self._batch_frame, mode="determinate"); self.batch_prog.pack(fill="x", pady=4)

        # 批量页操作按钮
        bb2 = tb.Frame(self._batch_frame); bb2.pack(fill="x", pady=6)
        RoundedButton(bb2, text="开始批量生产 / Start Batch", command=self._on_batch, width=200, height=36, bg_color="#0d6efd", fg_color="#ffffff", hover_color="#0b5ed7", radius=12).pack(side="left", padx=3)
        RoundedButton(bb2, text="取消", command=self._on_cancel, width=100, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="left", padx=3)

        # ═══════ 共享控件（两种模式都显示）═══
        self._shared_frame = tb.Frame(self.left_panel)

        # 选项
        opt = tb.Labelframe(self._shared_frame, text="选项 / Options", padding=8)
        opt.pack(fill="x", pady=6)
        self.tts_var = tk.BooleanVar(value=True); self.bgm_var = tk.BooleanVar(value=True); self.bgrp_var = tk.BooleanVar(value=True)
        tb.Checkbutton(opt, text="AI配音 / TTS", variable=self.tts_var).pack(side="left", padx=6)
        tb.Checkbutton(opt, text="自动BGM", variable=self.bgm_var).pack(side="left", padx=6)
        tb.Checkbutton(opt, text="B组混剪", variable=self.bgrp_var).pack(side="left", padx=6)

        # 配音语速
        sf = tb.Frame(self._shared_frame); sf.pack(fill="x", pady=2)
        tb.Label(sf, text="配音语速:").pack(side="left", padx=2)
        self.speed_var = tk.DoubleVar(value=1.1)
        sl = tb.Scale(sf, from_=0.8, to=2.0, variable=self.speed_var, orient="horizontal", bootstyle="primary")
        sl.pack(side="left", fill="x", expand=True, padx=4)
        self.speed_lbl = tb.Label(sf, text="1.1x"); self.speed_lbl.pack(side="left")
        sl.configure(command=lambda v, l=self.speed_lbl: l.config(text=f"{float(v):.1f}x"))

        # BGM音量
        bf2 = tb.Frame(self._shared_frame); bf2.pack(fill="x", pady=2)
        tb.Label(bf2, text="BGM音量:").pack(side="left", padx=2)
        self.bgm_vol_var = tk.DoubleVar(value=0.4)
        sl2 = tb.Scale(bf2, from_=0.05, to=1.0, variable=self.bgm_vol_var, orient="horizontal", bootstyle="primary")
        sl2.pack(side="left", fill="x", expand=True, padx=4)
        self.bgm_lbl = tb.Label(bf2, text="40%"); self.bgm_lbl.pack(side="left")
        sl2.configure(command=lambda v, l=self.bgm_lbl: l.config(text=f"{int(float(v)*100)}%"))

        # 进度条
        self.gen_progress = tb.Progressbar(self._shared_frame, mode="determinate")
        self.gen_progress.pack(fill="x", pady=4)
        self.prog_lbl = tb.Label(self._shared_frame, text=""); self.prog_lbl.pack()

        # 文件夹 + 按钮
        self._gen_fp = tb.Labelframe(self._shared_frame, text="素材文件夹 (点击展开)")
        self._gen_fp.pack(fill="x", pady=4)
        self._gen_fp_frame = tb.Frame(self._gen_fp)
        self._gen_folder_visible = False
        self._gen_folder_ui_built = False
        tb.Button(self._gen_fp, text="加载素材库 / Load Library", command=self._toggle_gen_folders).pack(pady=3)

        # 单次模式操作按钮
        btn_single = tb.Frame(self._single_frame); btn_single.pack(fill="x", pady=8)
        RoundedButton(btn_single, text="生成视频草稿", command=self._on_generate, width=160, height=38, bg_color="#0d6efd", fg_color="#ffffff", hover_color="#0b5ed7", radius=12).pack(side="left", padx=3)
        RoundedButton(btn_single, text="取消", command=self._on_cancel, width=80, height=38, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=12).pack(side="left", padx=3)
        RoundedButton(btn_single, text="清空", command=self._on_clear, width=80, height=38, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=12).pack(side="left", padx=3)

        self._shared_frame.pack(fill="x")

        # 默认显示单次模式
        self._single_frame.pack(fill="x")

    def _on_mode_change(self):
        """切换单次/批量模式"""
        if self.gen_mode.get() == "single":
            self._batch_frame.pack_forget()
            self._single_frame.pack(fill="x")
        else:
            self._single_frame.pack_forget()
            self._batch_frame.pack(fill="x")


    def _on_generate(self):
        if self._generating: self._log("[WARN] 正在生成中..."); return
        kw = self.kw_entry.get().strip()
        if not kw: messagebox.showwarning("提示","请输入关键词"); return
        self._update_recent(kw); self._generating = True; self._cancel_event.clear()
        self.gen_progress["value"] = 0; self.prog_lbl.config(text="0%")
        self._log(f"开始: {kw}"); self._set_status("生成中...")
        def _pcb(step,total,msg):
            self.root.after(0, lambda: (self.gen_progress.configure(value=step,maximum=total),
                self.prog_lbl.config(text=f"{int(step/total*100)}%"), self._set_status(msg)))
        def _task():
            ve = _get_ve()
            ve.DEFAULT_VOICE_RATE = self.speed_var.get(); ve.BGM_VOLUME = self.bgm_vol_var.get()
            ve.ENABLE_B_GROUP_MIX = self.bgrp_var.get()
            sf = [n for n,v in self._gen_folder_check_vars.items() if v.get()] if self._gen_folder_check_vars else []
            if sf:
                import os as _os
                _os.environ["TREECUT_SELECTED_FOLDERS"] = ",".join(sf)
                self._log(f"[Filter] 使用 {len(sf)} 个文件夹")
            try:
                ct_val = self.copy_text.get("1.0","end-1c").strip() or None
                r = ve.run(keyword=kw, copy_text_override=ct_val, generate_tts=self.tts_var.get(), auto_bgm=self.bgm_var.get(), progress_callback=_pcb)
                self.root.after(0, lambda: self._on_done(r))
            except Exception as e: self.root.after(0, lambda: self._on_error(str(e)))
        threading.Thread(target=_task, daemon=True).start()

    def _on_done(self, r):
        self._generating = False
        if r and "draft_dir" in r: self._log(f"完成: {r['draft_dir']}"); self._set_status("完成 Done")
        else: self._log(f"完成: {r}"); self._set_status("完成 Done")
        try: self._save_log()
        except Exception as _e: from utils.logging import log_warning; log_warning('desktop', str(_e)[:80])

    def _on_error(self, e):
        self._generating = False
        self._log(f"ERROR: {e}")
        self._set_status("错误")
        try:
            from utils.error_helper import handle_error
            handle_error(e, parent=self.root, log_callback=self._log)
        except Exception: pass

    def _on_cancel(self):
        if self._generating: self._cancel_event.set(); self._log("已取消"); self._set_status("已取消")

    def _on_clear(self):
        self.kw_entry.set(""); self.copy_text.delete("1.0","end")
        self.batch_text.delete("1.0","end")  # also clear batch text
        self.tts_var.set(True); self.bgm_var.set(True); self.bgrp_var.set(True)
        self.gen_progress["value"]=0; self.prog_lbl.config(text=""); self.log_area.delete("1.0","end")
        self._set_status("已清空")

    def _log(self, msg):
        self.log_area.insert("end", f"{datetime.now().strftime('%H:%M:%S')} {msg}\n"); self.log_area.see("end")

    def _save_log(self):
        try:
            lf = Path(__file__).parent.parent / "generate_log.txt"
            with open(lf,"a",encoding="utf-8") as f: f.write(f"\n=== {datetime.now().isoformat()[:19]} ===\n{self.log_area.get('1.0','end-1c')}\n")
        except Exception as _e: from utils.logging import log_warning; log_warning('desktop', str(_e)[:80])

    def _update_recent(self, kw):
        if kw in self.recent_kw: self.recent_kw.remove(kw)
        self.recent_kw.insert(0, kw); self.recent_kw = self.recent_kw[:10]
        self._save_json("recent_kw.json", self.recent_kw); self.kw_entry['values'] = self.recent_kw

    # ── 批量生产 ──

    def _auto_fill_batch(self):
        raw_text = self.batch_text.get("1.0", "end-1c")
        from core.script_utils import split_scripts
        force = self.batch_force_line.get()
        raw_lines = [l for l in raw_text.splitlines() if l.strip()]
        scripts = split_scripts(raw_text, force_by_line=force)
        self._log(f"[AutoFill] {len(raw_lines)}行 -> {len(scripts)}条脚本 (force_by_line={force})")
        # 多行但只识别出1个脚本 → 可能是逐行独立脚本，提示勾选强制按行
        if len(raw_lines) > 3 and len(scripts) == 1 and not force:
            if messagebox.askyesno("提示",
                f"检测到 {len(raw_lines)} 行文本但只识别出 1 条脚本。\n\n"
                "如果每行是一个独立脚本，请勾选「强制按行」后重新识别。\n\n"
                "是否自动勾选强制按行并重新识别？"):
                self.batch_force_line.set(True)
                scripts = split_scripts(raw_text, force_by_line=True)
                self._log(f"[AutoFill] retry force_by_line: {len(scripts)}条")
        if not scripts:
            messagebox.showinfo("提示", "未识别到有效文案。\n用空行分隔不同脚本，或勾选「强制按行」。")
            return
        n = min(len(scripts), 30)
        self.batch_slot_count.set(n)
        self._build_slots()
        for i, txt in enumerate(self.script_slots):
            if i < len(scripts):
                txt.delete("1.0", "end")
                txt.insert("1.0", scripts[i])
            else:
                txt.delete("1.0", "end")

    def _batch_gen(self):
        raw_text = self.batch_text.get("1.0", "end-1c")
        from core.script_utils import split_scripts
        force = self.batch_force_line.get()
        scripts = split_scripts(raw_text, force_by_line=force)
        print(f"[DEBUG] batch_gen: {len(scripts)} scripts")
        if not scripts:
            messagebox.showinfo("提示", "未识别到有效文案。\n用空行分隔不同脚本，或勾选强制按行。")
            return
        self.batch_tree.delete(*self.batch_tree.get_children())
        self.batch_prog["maximum"] = len(scripts); self.batch_prog["value"] = 0
        self._set_status(f"批量: 0/{len(scripts)}")
        self._log(f"[Gen] {len(scripts)}条")
        threading.Thread(target=lambda: self._run_batch(len(scripts), scripts), daemon=True).start()

    def _build_slots(self):
        for w in self.slots_frame.winfo_children(): w.destroy()
        self.script_slots = []
        n = min(self.batch_slot_count.get(), 30)
        self.batch_slot_count.set(n)
        for i in range(n):
            f = tb.Frame(self.slots_frame); f.pack(fill="x", pady=1)
            tb.Label(f, text=f"脚本{i + 1}:").pack(side="left")
            txt = tb.Text(f, height=2, font=("Microsoft YaHei", 11))
            txt.pack(side="left", fill="x", expand=True, padx=4)
            self.script_slots.append(txt)

    def _on_batch(self):
        lines = []
        for txt in self.script_slots:
            c = txt.get("1.0", "end-1c").strip()
            if c: lines.append(c)
        if not lines:
            paste = self.batch_text.get("1.0", "end-1c").strip()
            if paste:
                from core.script_utils import split_scripts
                lines = split_scripts(paste, force_by_line=self.batch_force_line.get())
        if not lines:
            messagebox.showinfo("提示", "未找到任何文案。\n请先粘贴内容 -> 识别并填充 -> 再点击开始批量生产")
            return
        self.batch_tree.delete(*self.batch_tree.get_children())
        # Pre-insert all rows with "等待中" status
        for idx, line in enumerate(lines, 1):
            preview = line.replace("\n", " ")[:40]
            self.batch_tree.insert("", "end", iid=str(idx),
                values=(idx, "[WAIT] 等待中", preview))
        self.batch_prog["maximum"] = len(lines); self.batch_prog["value"] = 0
        self._set_status(f"批量: 0/{len(lines)}")
        self._log(f"开始批量生产: {len(lines)}条")
        threading.Thread(target=lambda: self._run_batch(len(lines), lines), daemon=True).start()

    def _run_batch(self, count, lines):
        ve = _get_ve(); ve.DEFAULT_VOICE_RATE = self.speed_var.get()
        self._log(f"批量开始: {count}个视频")
        ok_count = [0]  # mutable counter for closure
        for i in range(count):
            idx = i + 1
            if self._cancel_event.is_set():
                self.root.after(0, lambda n=idx: self.batch_tree.set(str(n), "status", "已取消"))
                self._log(f"  [{idx}] 已取消"); break
            # Update status to "生成中"
            self.root.after(0, lambda n=idx: self.batch_tree.set(str(n), "status", "[RUN] 生成中"))
            try:
                preview = (lines[i] if i < len(lines) else "AI")[:40]
                ve.run(keyword="batch", copy_text_override=lines[i] if i<len(lines) else None, generate_tts=True, auto_bgm=True)
                ok_count[0] += 1
                self.root.after(0, lambda n=idx, p=preview: (
                    self.batch_tree.set(str(n), "status", "[OK] 成功"),
                    self.batch_tree.set(str(n), "preview", p)
                ))
                self._log(f"  [{idx}/{count}] OK")
            except Exception as e:
                emsg = str(e)[:40]
                self.root.after(0, lambda n=idx, e=emsg: self.batch_tree.set(str(n), "status", f"[FAIL] {e}"))
                self._log(f"  [{idx}/{count}] FAIL: {emsg}")
            self.root.after(0, lambda n=idx: (self.batch_prog.configure(value=n), self._set_status(f"批量 {n}/{count}")))
            time.sleep(0.5)
        self._log(f"批量完成: {ok_count[0]}/{count} 成功")
        self.root.after(0, lambda: (self._set_status("完成"), messagebox.showinfo("完成",f"生成 {ok_count[0]}/{count} 个视频")))

    def _toggle_gen_folders(self):
        """生成页面 — 加载素材库"""
        if self._gen_folder_visible:
            self._gen_fp_frame.pack_forget()
            self._gen_fp.configure(text="素材文件夹 (点击展开)")
            self._gen_folder_visible = False
            return
        if not self._gen_folder_ui_built:
            self._gen_folder_ui_built = True
            for w in self._gen_fp_frame.winfo_children(): w.destroy()
            pts = _get_folders_fast()
            if pts:
                canvas = tk.Canvas(self._gen_fp_frame, height=180, highlightthickness=0, bg="#c8e6c9")
                sb = tb.Scrollbar(self._gen_fp_frame, orient="vertical", command=canvas.yview, bootstyle="round")
                ff = tk.Frame(canvas, bg="#c8e6c9")
                ff.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
                canvas.create_window((0,0), window=ff, anchor="nw", width=700)
                canvas.configure(yscrollcommand=sb.set); canvas.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
                def _mw(e): canvas.yview_scroll(int(-1*(e.delta/120)),"units")
                canvas.bind("<MouseWheel>",_mw); ff.bind("<MouseWheel>",_mw)
                self._gen_folder_check_vars = {}
                row, col = 0, 0
                hist = self._load_json("folder_selection.json",{}).get("selected",[])
                for p in pts:
                    v = tk.BooleanVar(value=p["name"] in hist if hist else True)
                    self._gen_folder_check_vars[p["name"]] = v
                    tb.Checkbutton(ff, text=f"{p['name']}({p['count']})", variable=v).grid(row=row, column=col, sticky="w", padx=3)
                    col += 1
                    if col >= 4: col = 0; row += 1
                ctrl = tb.Frame(self._gen_fp_frame); ctrl.pack(fill="x", pady=4)
                RoundedButton(ctrl, text="全选", command=lambda: [v.set(True) for v in self._gen_folder_check_vars.values()], width=100, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="left", padx=2)
                RoundedButton(ctrl, text="全不选", command=lambda: [v.set(False) for v in self._gen_folder_check_vars.values()], width=100, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="left", padx=2)
                RoundedButton(ctrl, text="刷新", command=self._refresh_gen_folders, width=100, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="left", padx=2)
        self._gen_fp_frame.pack(fill="x", padx=4, pady=4)
        self._gen_fp.configure(text="素材文件夹")
        self._gen_folder_visible = True

    def _refresh_gen_folders(self):
        global _folder_cache
        with _cache_lock: _folder_cache = None
        self._gen_folder_ui_built = False
        self._gen_folder_visible = False
        self._toggle_gen_folders()

    def _toggle_folders(self):
        """素材盘检索页 — 加载素材库"""
        if self.folder_panel_visible:
            self.fp_frame.pack_forget(); self.fp.configure(text="素材文件夹 (点击展开)"); self.folder_panel_visible = False; return
        if not self._folder_ui_built:
            self._folder_ui_built = True
            for w in self.fp_frame.winfo_children(): w.destroy()
            pts = _get_folders_fast()
            if pts:
                canvas = tk.Canvas(self.fp_frame, height=180, highlightthickness=0, bg="#c8e6c9")
                sb = tb.Scrollbar(self.fp_frame, orient="vertical", command=canvas.yview, bootstyle="round")
                ff = tk.Frame(canvas, bg="#c8e6c9")
                ff.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
                canvas.create_window((0,0), window=ff, anchor="nw", width=700)
                canvas.configure(yscrollcommand=sb.set); canvas.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
                def _mw(e): canvas.yview_scroll(int(-1*(e.delta/120)),"units")
                canvas.bind("<MouseWheel>",_mw); ff.bind("<MouseWheel>",_mw)
                self.folder_check_vars = {}
                row, col = 0, 0
                hist = self._load_json("folder_selection.json",{}).get("selected",[])
                for p in pts:
                    v = tk.BooleanVar(value=p["name"] in hist if hist else True)
                    self.folder_check_vars[p["name"]] = v
                    tb.Checkbutton(ff, text=f"{p['name']}({p['count']})", variable=v).grid(row=row, column=col, sticky="w", padx=3)
                    col += 1
                    if col >= 4: col = 0; row += 1
                ctrl = tb.Frame(self.fp_frame); ctrl.pack(fill="x", pady=4)
                RoundedButton(ctrl, text="全选", command=lambda: [v.set(True) for v in self.folder_check_vars.values()], width=100, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="left", padx=2)
                RoundedButton(ctrl, text="全不选", command=lambda: [v.set(False) for v in self.folder_check_vars.values()], width=100, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="left", padx=2)
                RoundedButton(ctrl, text="刷新", command=self._refresh_folders, width=100, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="left", padx=2)
        self.fp_frame.pack(fill="x", padx=4, pady=4); self.fp.configure(text="素材文件夹"); self.folder_panel_visible = True

    def _refresh_folders(self):
        global _folder_cache
        with _cache_lock: _folder_cache = None
        with _ui_state_lock:
            self._folder_ui_built = False
            self.folder_panel_visible = False
        self._toggle_folders()

    def _toggle_batch_folders(self):
        if self.batch_fp_visible:
            self.batch_folder_frame.pack_forget(); self.batch_fp_visible = False; return
        for w in self.batch_folder_frame.winfo_children(): w.destroy()
        pts = _get_folders_fast()
        if pts:
            canvas = tk.Canvas(self.batch_folder_frame, height=120, highlightthickness=0, bg="#c8e6c9")
            sb = tb.Scrollbar(self.batch_folder_frame, orient="vertical", command=canvas.yview, bootstyle="round")
            ff = tk.Frame(canvas, bg="#c8e6c9")
            ff.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.create_window((0,0), window=ff, anchor="nw", width=700)
            canvas.configure(yscrollcommand=sb.set); canvas.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
            def _mw(e): canvas.yview_scroll(int(-1*(e.delta/120)),"units")
            canvas.bind("<MouseWheel>",_mw); ff.bind("<MouseWheel>",_mw)
            self.batch_folder_vars = {}; row,col=0,0
            for p in pts:
                v = tk.BooleanVar(value=True); self.batch_folder_vars[p["name"]]=v
                tb.Checkbutton(ff, text=f"{p['name']}({p['count']})", variable=v).grid(row=row,column=col,sticky="w",padx=3)
                col+=1
                if col>=4: col=0; row+=1
            ctrl = tb.Frame(self.batch_folder_frame); ctrl.pack(fill="x",pady=2)
            RoundedButton(ctrl, text="全选", command=lambda: [v.set(True) for v in self.batch_folder_vars.values()], width=100, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="left",padx=2)
            RoundedButton(ctrl, text="全不选", command=lambda: [v.set(False) for v in self.batch_folder_vars.values()], width=100, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="left",padx=2)
        self.batch_folder_frame.pack(fill="x"); self.batch_fp_visible = True

    def _on_usage(self):
        """素材使用统计"""
        try:
            self._show_usage_stats()
        except Exception:
            pass
    # ═══════════════ TAB: 素材盘检索 (融合素材库+全盘检索+标注+学习日志) ═══════════════

    # ═══════════════ TAB: 素材盘检索 (v11.4 横向工具栏+左侧导航+右侧面板) ═══════════════
    def _build_material_panel(self):
        main_frame = tb.Frame(self.nb, padding=4)
        self.nb.add(main_frame, text="素材盘检索")

        # ═══════ TOP: 横向工具栏 ═══════
        top_bar = tb.Frame(main_frame)
        top_bar.pack(fill="x", pady=(0,4))

        # 第一行
        row1 = tb.Frame(top_bar); row1.pack(fill="x", pady=1)
        RoundedButton(row1, text="浏览文件夹", command=self._disk_browse,
                     height=30, bg_color="#e0e0e0", fg_color="#212529",
                     hover_color="#d0e0ff", radius=6).pack(side="left", padx=2)
        RoundedButton(row1, text="快速扫描常用位置", command=self._disk_quick,
                     height=30, bg_color="#e0e0e0", fg_color="#212529",
                     hover_color="#d0e0ff", radius=6).pack(side="left", padx=2)
        RoundedButton(row1, text="全盘素材扫描", command=self._on_scan_all,
                     height=30, bg_color="#28a745", fg_color="#ffffff",
                     hover_color="#218838", radius=6).pack(side="left", padx=2)
        RoundedButton(row1, text="重建FAISS索引", command=self._rebuild_faiss,
                     height=30, bg_color="#6f42c1", fg_color="#ffffff",
                     hover_color="#5a32a3", radius=6).pack(side="left", padx=2)
        RoundedButton(row1, text="刷新统计", command=self._on_refresh_lib,
                     height=30, bg_color="#0d6efd", fg_color="#ffffff",
                     hover_color="#0b5ed7", radius=6).pack(side="left", padx=2)
        RoundedButton(row1, text="清除缓存", command=self._clear_lib_cache,
                     height=30, bg_color="#e0e0e0", fg_color="#212529",
                     hover_color="#d0e0ff", radius=6).pack(side="left", padx=2)

        self.disk_status = tb.Label(top_bar, text="就绪", font=("Microsoft YaHei",9),
                                     foreground="#6d6d6d")
        self.disk_status.pack(side="right", padx=6)

        # ═══════ BOTTOM: 左右分栏 ═══════
        body_frame = tb.Frame(main_frame)
        body_frame.pack(fill="both", expand=True)

        # 左侧导航 (Listbox 风格)
        left_nav = tb.Frame(body_frame, width=140)
        left_nav.pack(side="left", fill="y", padx=(0,4))
        left_nav.pack_propagate(False)

        # 右侧内容区
        self._material_right = tb.Frame(body_frame)
        self._material_right.pack(side="right", fill="both", expand=True)

        # 预构建四个面板
        self._panel_video = tb.Frame(self._material_right)
        self._panel_libstats = tb.Frame(self._material_right)
        self._panel_anno = tb.Frame(self._material_right)
        self._panel_learn = tb.Frame(self._material_right)

        self._build_video_preview_panel(self._panel_video)
        self._build_library_stats_panel(self._panel_libstats)
        self._build_frame_annotation_panel(self._panel_anno)
        self._build_learning_log_panel(self._panel_learn)

        # 导航按钮
        self._nav_btns = {}
        nav_items = [
            ("视频预览", self._panel_video),
            ("素材库统计", self._panel_libstats),
            ("帧级标注", self._panel_anno),
            ("学习日志", self._panel_learn),
        ]
        for name, panel in nav_items:
            btn = RoundedButton(left_nav, text=name,
                              command=lambda p=panel: self._switch_material_panel(p),
                              height=36, bg_color="#e9ecef", fg_color="#1b5e20",
                              hover_color="#c8e6c9", radius=6)
            btn.pack(fill="x", padx=4, pady=2)
            self._nav_btns[name] = btn

        # 默认显示视频预览
        self._switch_material_panel(self._panel_video)

    def _switch_material_panel(self, panel):
        """切换右侧面板显示"""
        for p in [self._panel_video, self._panel_libstats, self._panel_anno, self._panel_learn]:
            p.pack_forget()
        panel.pack(fill="both", expand=True)
        # 高亮当前按钮
        current_name = None
        for name, p in [("视频预览",self._panel_video),("素材库统计",self._panel_libstats),
                         ("帧级标注",self._panel_anno),("学习日志",self._panel_learn)]:
            if p is panel:
                current_name = name
                break
        for name, btn in self._nav_btns.items():
            if name == current_name:
                btn.configure(bg_color="#2e7d32", fg_color="#ffffff")
            else:
                btn.configure(bg_color="#e9ecef", fg_color="#1b5e20")

    def _build_video_preview_panel(self, parent):
        info_row = tb.Frame(parent); info_row.pack(fill="x", pady=(0,4))
        self._disk_preview_status = tb.Label(info_row, text="从左侧选择文件夹加载视频",
                                             font=("Microsoft YaHei",9), foreground="#6d6d6d")
        self._disk_preview_status.pack(side="left")
        RoundedButton(info_row, text="生成选中视频", command=self._disk_gen,
                     height=34, bg_color="#0d6efd", fg_color="#ffffff",
                     hover_color="#0b5ed7", radius=8).pack(side="right", padx=4)

        self._disk_preview_tree = tb.Treeview(parent, columns=("name","size","dur"), show="headings")
        self._disk_preview_tree.heading("name", text="文件名"); self._disk_preview_tree.column("name", width=350)
        self._disk_preview_tree.heading("size", text="大小"); self._disk_preview_tree.column("size", width=80)
        self._disk_preview_tree.heading("dur", text="时长"); self._disk_preview_tree.column("dur", width=80)
        self._disk_preview_tree.pack(fill="both", expand=True)
        self._disk_preview_tree.bind("<Double-1>", lambda e: self._disk_gen())

    def _build_library_stats_panel(self, parent):
        btn_row = tb.Frame(parent); btn_row.pack(fill="x", pady=(0,4))
        RoundedButton(btn_row, text="刷新统计", command=self._on_refresh_lib,
                     height=34, bg_color="#0d6efd", fg_color="#ffffff",
                     hover_color="#0b5ed7", radius=8).pack(side="left", padx=2)
        RoundedButton(btn_row, text="清除缓存", command=self._clear_lib_cache,
                     height=34, bg_color="#e0e0e0", fg_color="#212529",
                     hover_color="#d0ee0ff", radius=8).pack(side="left", padx=2)
        RoundedButton(btn_row, text="使用统计", command=self._show_usage_stats,
                     height=34, bg_color="#e0e0e0", fg_color="#212529",
                     hover_color="#d0e0ff", radius=8).pack(side="left", padx=2)
        RoundedButton(btn_row, text="加载素材库", command=self._toggle_folders,
                     height=34, bg_color="#e0e0e0", fg_color="#212529",
                     hover_color="#d0e0ff", radius=8).pack(side="left", padx=2)
        self.lib_status = tb.Label(btn_row, text="", font=("Microsoft YaHei",9), foreground="#6d6d6d")
        self.lib_status.pack(side="right", padx=6)

        self.fp = tb.Labelframe(parent, text="素材文件夹")
        self.fp.pack(fill="x", pady=4)
        self.fp_frame = tb.Frame(self.fp)
        self.fp.configure(text="素材文件夹 (点击「加载素材库」展开)")

        self.lib_tree = tb.Treeview(parent, columns=("name","cnt"), show="headings")
        self.lib_tree.heading("name", text="卖点名称"); self.lib_tree.column("name", width=400)
        self.lib_tree.heading("cnt", text="数量"); self.lib_tree.column("cnt", width=100)
        self.lib_tree.pack(fill="both", expand=True)
        # v11.4: 注册数据库变更回调 -> 刷新统计
        try:
            from core.database import db
            db.register_callback(lambda vp: self.root.after(0, self._on_refresh_lib))
        except Exception:
            pass

    def _build_frame_annotation_panel(self, parent):
        """帧级标注 —— FrameAnnotationTab 需要 Notebook 容器"""
        inner_nb = tb.Notebook(parent, bootstyle="light")
        inner_nb.pack(fill="both", expand=True)
        try:
            from ui.frame_annotation import FrameAnnotationTab
            FrameAnnotationTab(inner_nb, self)
        except Exception as e:
            import traceback
            traceback.print_exc()
            tb.Label(parent, text=f"标注模块加载失败: {e}",
                    font=("Microsoft YaHei", 10)).pack(pady=20)
            RoundedButton(parent, text="重试加载",
                         command=lambda: self._build_frame_annotation_panel(parent),
                         height=34, bg_color="#0d6efd", fg_color="#ffffff",
                         hover_color="#0b5ed7", radius=8).pack()

    def _build_learning_log_panel(self, parent):
        # 使用内部 Notebook 分上下两个区域
        inner_nb = tb.Notebook(parent, bootstyle="light")
        inner_nb.pack(fill="both", expand=True)

        # ---- 子页1: 反馈与黑名单 ----
        fb_parent = tb.Frame(inner_nb, padding=4)
        inner_nb.add(fb_parent, text="反馈管理")

        top_bar = tb.Frame(fb_parent); top_bar.pack(fill="x", pady=(0,4))
        RoundedButton(top_bar, text="刷新日志", command=self._ll_refresh,
                     height=34, bg_color="#0d6efd", fg_color="#ffffff",
                     hover_color="#0b5ed7", radius=8).pack(side="left", padx=2)
        RoundedButton(top_bar, text="一键拉黑低分素材", command=self._ll_block_low,
                     height=34, bg_color="#dc3545", fg_color="#ffffff",
                     hover_color="#c82333", radius=8).pack(side="left", padx=2)
        self.ll_status = tb.Label(top_bar, text="", font=("Microsoft YaHei",9), foreground="#6d6d6d")
        self.ll_status.pack(side="right", padx=6)

        fb_frame = tb.Labelframe(fb_parent, text="反馈记录", padding=4)
        fb_frame.pack(fill="both", expand=True, pady=(0,3))
        self.ll_feedback_tree = tb.Treeview(fb_frame,
            columns=("path","avg","count","last"), show="headings", height=6)
        self.ll_feedback_tree.heading("path", text="素材路径"); self.ll_feedback_tree.column("path", width=300)
        self.ll_feedback_tree.heading("avg", text="均分"); self.ll_feedback_tree.column("avg", width=50)
        self.ll_feedback_tree.heading("count", text="次数"); self.ll_feedback_tree.column("count", width=50)
        self.ll_feedback_tree.heading("last", text="最近反馈"); self.ll_feedback_tree.column("last", width=120)
        self.ll_feedback_tree.pack(fill="both", expand=True)

        low_frame = tb.Labelframe(fb_parent, text="低分素材管理", padding=4)
        low_frame.pack(fill="both", expand=True)
        self.ll_low_tree = tb.Treeview(low_frame,
            columns=("path","avg","count","blocked"), show="headings", height=4)
        self.ll_low_tree.heading("path", text="素材路径"); self.ll_low_tree.column("path", width=300)
        self.ll_low_tree.heading("avg", text="均分"); self.ll_low_tree.column("avg", width=50)
        self.ll_low_tree.heading("count", text="次数"); self.ll_low_tree.column("count", width=50)
        self.ll_low_tree.heading("blocked", text="拉黑"); self.ll_low_tree.column("blocked", width=50)
        self.ll_low_tree.pack(fill="both", expand=True)

        low_btn = tb.Frame(low_frame); low_btn.pack(fill="x", pady=2)
        RoundedButton(low_btn, text="拉黑选中", command=self._ll_block_selected,
                     height=34, bg_color="#dc3545", fg_color="#ffffff",
                     hover_color="#c82333", radius=8).pack(side="left", padx=2)
        RoundedButton(low_btn, text="取消拉黑", command=self._ll_unblock_selected,
                     height=34, bg_color="#28a745", fg_color="#ffffff",
                     hover_color="#218838", radius=8).pack(side="left", padx=2)

        # ---- 子页2: 后台扫描控制（嵌入式） ----
        scan_parent = tb.Frame(inner_nb, padding=4)
        inner_nb.add(scan_parent, text="后台扫描")

        # 扫描路径选择
        path_frame = tb.Labelframe(scan_parent, text="扫描目录", padding=4)
        path_frame.pack(fill="x", pady=(0,4))
        self._scan_paths_var = tk.StringVar(value="使用默认素材目录")
        path_row = tb.Frame(path_frame); path_row.pack(fill="x")
        tb.Label(path_row, textvariable=self._scan_paths_var, font=("Microsoft YaHei",9),
                foreground="#4a7c4f").pack(side="left", fill="x", expand=True)
        RoundedButton(path_row, text="选择目录", command=self._scan_choose_dir,
                     height=30, bg_color="#e0e0e0", fg_color="#212529",
                     hover_color="#d0e0ff", radius=8).pack(side="right", padx=2)
        RoundedButton(path_row, text="使用默认", command=self._scan_use_default_dirs,
                     height=30, bg_color="#e0e0e0", fg_color="#212529",
                     hover_color="#d0e0ff", radius=8).pack(side="right", padx=2)

        # 控制按钮
        ctrl_frame = tb.Frame(scan_parent); ctrl_frame.pack(fill="x", pady=4)
        self._scan_btn_start = RoundedButton(ctrl_frame, text="开始扫描",
                         command=self._start_embedded_scan,
                         height=34, bg_color="#0d6efd", fg_color="#ffffff",
                         hover_color="#0b5ed7", radius=8)
        self._scan_btn_start.pack(side="left", padx=2)
        self._scan_btn_pause = RoundedButton(ctrl_frame, text="暂停",
                         command=self._toggle_embedded_scan,
                         height=34, bg_color="#ffc107", fg_color="#212529",
                         hover_color="#e0a800", radius=8)
        self._scan_btn_pause.pack(side="left", padx=2)
        self._scan_btn_pause.configure(state="disabled")
        self._scan_btn_stop = RoundedButton(ctrl_frame, text="停止",
                         command=self._stop_embedded_scan,
                         height=34, bg_color="#dc3545", fg_color="#ffffff",
                         hover_color="#c82333", radius=8)
        self._scan_btn_stop.pack(side="left", padx=2)
        self._scan_btn_stop.configure(state="disabled")
        self._scan_status = tb.Label(ctrl_frame, text="就绪", font=("Microsoft YaHei",9),
                                     foreground="#6d6d6d")
        self._scan_status.pack(side="right", padx=6)

        # 进度条
        self._scan_progress = tb.Progressbar(scan_parent, mode="determinate", bootstyle="success")
        self._scan_progress.pack(fill="x", pady=2)
        self._scan_cur_file = tb.Label(scan_parent, text="",
                                      font=("Microsoft YaHei",9), foreground="#888")
        self._scan_cur_file.pack(anchor="w")

        # 实时日志
        log_frame = tb.Labelframe(scan_parent, text="扫描日志", padding=4)
        log_frame.pack(fill="both", expand=True, pady=(4,0))
        self._scan_log = scrolledtext.ScrolledText(log_frame, font=("Consolas",10),
                                                   height=12, bg="#1b1b1b", fg="#a5d6a7")
        self._scan_log.pack(fill="both", expand=True)

        # 初始化扫描状态
        self._scan_roots = None  # None=使用默认路径
        self._scan_running = False
        self._scan_paused = False
        self._scan_analyzer = None
        # v11.4: 注册数据库变更回调 -> 刷新学习日志
        try:
            from core.database import db
            db.register_callback(lambda vp: self.root.after(0, self._ll_refresh))
        except Exception:
            pass


    # ── 辅助方法 ──
    def _clear_lib_cache(self):
        _get_ve().MaterialCacheManager.invalidate()
        self.lib_status.config(text="缓存已清除")

    def _show_usage_stats(self):
        try:
            import io
            buf = io.StringIO(); old = sys.stdout; sys.stdout = buf
            _get_ve().MaterialUsageTracker.print_stats(top_n=20); sys.stdout = old
            stats_text = buf.getvalue() or "暂无记录"
            messagebox.showinfo("素材使用统计", stats_text[:1000])
        except Exception as e:
            self.lib_status.config(text=f"错误: {e}")

    def _on_refresh_lib(self):
        self.lib_tree.delete(*self.lib_tree.get_children())
        if not self._ve_ready: self.lib_status.config(text="加载中...")
        def _r():
            ve = _get_ve()
            try:
                pts = ve.list_available_selling_points()
                self.root.after(0, lambda: [
                    self.lib_tree.insert("","end",values=(p.get("original_name",""),p.get("mp4_count",0)))
                    for p in pts])
                self.root.after(0, lambda: self.lib_status.config(text=f"{len(pts)}个文件夹"))
            except Exception as e:
                self.root.after(0, lambda: self.lib_status.config(text=str(e)[:50]))
        threading.Thread(target=_r, daemon=True).start()

    def _rebuild_faiss(self):
        self._set_status("重建FAISS...")
        def _r():
            try:
                from core.library_builder import LibraryBuilder
                LibraryBuilder().build_faiss_index(progress=lambda m: self._log(m))
                self.root.after(0, lambda: messagebox.showinfo("完成","FAISS索引重建完成"))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误",str(e)))
        threading.Thread(target=_r, daemon=True).start()

    # ═══════════════════ 嵌入式后台扫描控制 ═══════════════════

    def _scan_choose_dir(self):
        path = filedialog.askdirectory(title="选择要扫描的素材文件夹")
        if path:
            self._scan_roots = [path]
            self._scan_paths_var.set(path)
            self._add_scan_log(f"扫描目录设为: {path}")

    def _scan_use_default_dirs(self):
        from core.config import SELLING_POINT_DIR, EFFECTS_DIR, B_GROUP_PATH
        self._scan_roots = None
        dirs = [SELLING_POINT_DIR, EFFECTS_DIR, B_GROUP_PATH]
        existing = [d for d in dirs if os.path.exists(d)]
        self._scan_paths_var.set(f"默认素材目录 ({len(existing)}个)")
        self._add_scan_log(f"使用默认目录: {', '.join(existing) if existing else '(均不存在)'}")

    def _add_scan_log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.root.after(0, lambda: (
            self._scan_log.insert("end", f"[{ts}] {msg}\n"),
            self._scan_log.see("end")
        ))

    def _set_scan_progress(self, current, total, status=""):
        self.root.after(0, lambda: (
            self._scan_progress.configure(value=current, maximum=max(1, total)),
            self._scan_status.configure(text=status),
            self._scan_cur_file.configure(text=status[:80] if status else "")
        ))

    def _start_embedded_scan(self):
        if self._scan_running and self._scan_paused:
            self._scan_paused = False
            if self._scan_analyzer:
                self._scan_analyzer.resume()
            self._scan_btn_pause.configure(text="暂停")
            self._add_scan_log("▶ 扫描已继续")
            return
        if self._scan_running:
            return

        from core.config import SELLING_POINT_DIR, EFFECTS_DIR, B_GROUP_PATH
        default_dirs = [SELLING_POINT_DIR, EFFECTS_DIR, B_GROUP_PATH]
        roots = self._scan_roots if self._scan_roots else default_dirs
        existing = [d for d in roots if os.path.exists(d)]

        if not existing:
            messagebox.showwarning("提示", "没有可用的扫描目录。请先选择文件夹。")
            return

        self._scan_running = True
        self._scan_paused = False
        self._scan_log.delete("1.0", "end")
        self._add_scan_log(f"=== 开始扫描 {len(existing)} 个目录 ===")
        for d in existing:
            self._add_scan_log(f"  {d}")

        self._scan_btn_start.configure(text="扫描中...")
        self._scan_btn_start.configure(state="disabled")
        self._scan_btn_pause.configure(state="normal")
        self._scan_btn_stop.configure(state="normal")

        threading.Thread(target=self._run_embedded_scan, args=(existing,), daemon=True).start()

    def _run_embedded_scan(self, root_dirs):
        try:
            from core.smart_analyzer import get_analyzer
            self._scan_analyzer = get_analyzer()
            self._scan_analyzer.reset_cancel()

            def _on_log(msg):
                self._add_scan_log(msg)

            def _on_progress(current, total, status):
                self._set_scan_progress(current, total, status)

            def _on_video_start(vp, idx, total):
                fname = Path(vp).name
                self._set_scan_progress(idx, total, f"[{idx}/{total}] {fname}")

            def _on_video_done(vp, result):
                fname = Path(vp).name
                island = result.get("island_found", 0)
                saved = result.get("saved", 0)
                if result.get("error"):
                    self._add_scan_log(f"  ❌ {fname}: {result['error']}")
                else:
                    self._add_scan_log(f"  ✓ {fname}: {saved}帧入库, {island}岛台帧")

            summary = self._scan_analyzer.scan_videos(
                root_dirs,
                on_log=_on_log,
                on_progress=_on_progress,
                on_video_start=_on_video_start,
                on_video_done=_on_video_done,
            )

            total = summary["total"]
            scanned = summary["scanned"]
            island = summary["island_total"]
            saved = summary["saved_total"]
            errors = len(summary["errors"])

            self._add_scan_log("=" * 40)
            self._add_scan_log(f"扫描完成: {scanned}/{total} 视频")
            self._add_scan_log(f"岛台帧: {island}, 入库: {saved}, 错误: {errors}")
            self._add_scan_log("💡 新入库素材将在下次生成时被检索到")
            if saved > 0:
                self._add_scan_log("💡 建议点击「重建FAISS索引」使新素材立即生效")

            self.root.after(0, self._ll_refresh)

        except Exception as e:
            self._add_scan_log(f"❌ 扫描异常: {e}")
            import traceback
            self._add_scan_log(traceback.format_exc()[:500])
        finally:
            self.root.after(0, self._on_scan_finished)

    def _on_scan_finished(self):
        self._scan_running = False
        self._scan_paused = False
        self._scan_btn_start.configure(text="开始扫描")
        self._scan_btn_start.configure(state="normal")
        self._scan_btn_pause.configure(state="disabled")
        self._scan_btn_stop.configure(state="disabled")
        self._scan_status.configure(text="完成")
        self._scan_analyzer = None
        # v11.4: 注册数据库变更回调 -> 刷新学习日志
        try:
            from core.database import db
            db.register_callback(lambda vp: self.root.after(0, self._ll_refresh))
        except Exception:
            pass

    def _toggle_embedded_scan(self):
        if not self._scan_running:
            return
        if self._scan_paused:
            self._scan_paused = False
            if self._scan_analyzer:
                self._scan_analyzer.resume()
            self._scan_btn_pause.configure(text="暂停")
            self._add_scan_log("▶ 扫描已继续")
        else:
            self._scan_paused = True
            if self._scan_analyzer:
                self._scan_analyzer.pause()
            self._scan_btn_pause.configure(text="继续")
            self._add_scan_log("⏸ 扫描已暂停")

    def _stop_embedded_scan(self):
        if not self._scan_running:
            return
        if self._scan_analyzer:
            self._scan_analyzer.cancel()
        self._scan_running = False
        self._scan_paused = False
        self._scan_btn_start.configure(state="normal")
        self._scan_btn_pause.configure(state="disabled")
        self._scan_btn_stop.configure(state="disabled")
        self._add_scan_log("⏹ 扫描已停止")

    # ── 学习日志辅助方法 ──
    def _ll_refresh(self):
        try:
            from core.database import db
            self.ll_feedback_tree.delete(*self.ll_feedback_tree.get_children())
            stats = db.get_all_feedback_stats(limit=50)
            for s in stats:
                self.ll_feedback_tree.insert("", "end", values=(
                    s["path"][:70], f"{s['avg_rating']:.2f}", s["count"],
                    (s.get("last_feedback","") or "")[:19]))
            self.ll_low_tree.delete(*self.ll_low_tree.get_children())
            low_mats = db.get_lowest_rated_materials(limit=20)
            for m in low_mats:
                path = m["path"]
                blocked = db.is_material_blocked(path)
                self.ll_low_tree.insert("", "end", values=(
                    path[:70], f"{m['avg_rating']:.2f}", m["count"], "是" if blocked else "否"))
            self.ll_status.config(text=f"已加载: {len(stats)}条反馈, {len(low_mats)}个低分素材")
        except Exception as e:
            self.ll_status.config(text=f"加载失败: {e}")

    def _ll_block_low(self):
        try:
            from core.database import db
            low_mats = db.get_lowest_rated_materials(limit=50)
            count = 0
            for m in low_mats:
                if not db.is_material_blocked(m["path"]):
                    db.block_material(m["path"])
                    count += 1
            messagebox.showinfo("完成", f"已拉黑 {count} 个低分素材")
            self._ll_refresh()
        except Exception as e:
            messagebox.showerror("错误", f"拉黑失败: {e}")

    def _ll_block_selected(self):
        sel = self.ll_low_tree.selection()
        if not sel: return
        try:
            from core.database import db
            count = 0
            all_low = db.get_lowest_rated_materials(limit=20)
            for item in sel:
                path_val = self.ll_low_tree.item(item, "values")[0]
                for m in all_low:
                    if m["path"][-len(path_val):] == path_val or path_val in m["path"]:
                        db.block_material(m["path"]); count += 1; break
            messagebox.showinfo("完成", f"已拉黑 {count} 个素材"); self._ll_refresh()
        except Exception as e:
            messagebox.showerror("错误", f"拉黑失败: {e}")

    def _ll_unblock_selected(self):
        sel = self.ll_low_tree.selection()
        if not sel: return
        try:
            from core.database import db
            count = 0
            all_low = db.get_lowest_rated_materials(limit=20)
            for item in sel:
                path_val = self.ll_low_tree.item(item, "values")[0]
                for m in all_low:
                    if m["path"][-len(path_val):] == path_val or path_val in m["path"]:
                        with db.get_connection() as conn:
                            conn.execute("UPDATE materials SET blocked=0 WHERE video_path=?", (m["path"],))
                        count += 1; break
            messagebox.showinfo("完成", f"已取消拉黑 {count} 个素材"); self._ll_refresh()
        except Exception as e:
            messagebox.showerror("错误", f"取消失败: {e}")

    def _disk_browse(self):
        path = filedialog.askdirectory(title="选择包含视频的文件夹")
        if path: self._load_disk_videos(path)

    def _disk_quick(self):
        self.disk_status.config(text="扫描常用位置...")
        def _s():
            from core.drive_scanner import get_scanner
            entries = get_scanner().get_quick_scan()
            if entries:
                # 自动展开第一个
                path = entries[0].path
                self.root.after(0, lambda: self._load_disk_videos(path))
            self.root.after(0, lambda: self.disk_status.config(text="扫描完成"))
        threading.Thread(target=_s, daemon=True).start()

    def _load_disk_videos(self, path):
        self.disk_vids.delete(*self.disk_vids.get_children())
        if hasattr(self, '_disk_preview_tree'):
            self._disk_preview_tree.delete(*self._disk_preview_tree.get_children())
        self.disk_status.config(text=f"加载中: {path[:50]}...")
        if hasattr(self, '_disk_preview_status'):
            self._disk_preview_status.config(text=f"加载: {Path(path).name}")
        def _l():
            from core.drive_scanner import get_scanner
            vids = get_scanner().list_videos(path)[:300]
            def _fill():
                for v in vids:
                    vals = (v.name[:60], f"{v.size_mb:.1f}MB", v.duration_str)
                    self.disk_vids.insert("","end", values=vals, tags=(v.path,))
                    if hasattr(self, '_disk_preview_tree'):
                        self._disk_preview_tree.insert("","end", values=vals, tags=(v.path,))
                self.disk_status.config(text=f"{len(vids)}个视频")
                if hasattr(self, '_disk_preview_status'):
                    self._disk_preview_status.config(text=f"{len(vids)}个视频 已加载")
            self.root.after(0, _fill)
        threading.Thread(target=_l, daemon=True).start()

    def _disk_gen(self):
        # Try preview tree first, then left panel tree
        tree = getattr(self, '_disk_preview_tree', None) or self.disk_vids
        sel = tree.selection()
        if not sel:
            sel = self.disk_vids.selection()  # fallback to left panel
        if sel:
            # Get the tree that actually has the selection
            source_tree = tree if tree.selection() else self.disk_vids
            path = source_tree.item(sel[0], "tags")[0]; name = Path(path).stem
            self._set_status(f"生成中: {name}")
            threading.Thread(target=lambda: (
                _get_ve().run(keyword=name, generate_tts=True, auto_bgm=True),
                self.root.after(0, lambda: self._set_status("完成"))
            ), daemon=True).start()
        else: messagebox.showinfo("提示","请先双击或选择一个视频")



    # ═══════════════ TAB 6: 历史记录 ═══════════════
    def _build_history(self):
        t = tb.Frame(self.nb, padding=10); self.nb.add(t, text="历史 / History")
        bf = tb.Frame(t); bf.pack(fill="x", pady=4)
        RoundedButton(bf, text="刷新", command=self._load_hist, width=100, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="left", padx=3)
        RoundedButton(bf, text="打开选中", command=self._open_hist, width=100, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="left", padx=3)
        RoundedButton(bf, text="素材反馈", command=self._show_material_feedback, width=100, height=34, bg_color="#0d6efd", fg_color="#ffffff", hover_color="#0b5ed7", radius=10).pack(side="left", padx=3)
        self.hist_tree = tb.Treeview(t, columns=("time","name","path"), show="headings")
        self.hist_tree.heading("time",text="时间"); self.hist_tree.column("time",width=100)
        self.hist_tree.heading("name",text="草稿"); self.hist_tree.column("name",width=250)
        self.hist_tree.heading("path",text="路径"); self.hist_tree.column("path",width=400)
        self.hist_tree.pack(fill="both",expand=True)
        self.hist_tree.bind("<Double-1>", lambda e: self._show_material_feedback())

    def _load_hist(self):
        self.hist_tree.delete(*self.hist_tree.get_children())
        from core.config import OUTPUT_DRAFT_DIR, JIANGYING_DRAFT_DIR
        dirs = [Path(OUTPUT_DRAFT_DIR), Path(JIANGYING_DRAFT_DIR)]
        for d in dirs:
            if d.exists():
                for dd in sorted(d.iterdir(), key=lambda x:x.stat().st_mtime, reverse=True)[:50]:
                    if dd.is_dir():
                        mt = datetime.fromtimestamp(dd.stat().st_mtime).strftime("%m-%d %H:%M")
                        self.hist_tree.insert("","end",values=(mt,dd.name[:40],str(dd)))
        self._set_status("完成")

    def _open_hist(self):
        sel = self.hist_tree.selection()
        if sel:
            path = self.hist_tree.item(sel[0],"values")[2]
            if os.path.exists(path): os.startfile(path)

    def _show_material_feedback(self):
        """显示选中草稿的素材列表与反馈界面 (v11.2)"""
        sel = self.hist_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在历史列表中双击或选中一条记录")
            return
        draft_dir = self.hist_tree.item(sel[0], "values")[2]
        if not os.path.isdir(draft_dir):
            messagebox.showerror("错误", "草稿目录不存在")
            return

        # 读取 video_metadata.json
        meta_path = os.path.join(draft_dir, "video_metadata.json")
        video_log_id = None
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                video_log_id = meta.get("video_log_id")
            except Exception:
                pass

        if not video_log_id:
            messagebox.showinfo("提示", "该草稿没有关联的素材日志（可能是旧版本生成的）")
            return

        # 从数据库获取素材列表
        try:
            from core.database import db
            materials = db.get_video_materials(video_log_id)
            video_log = db.get_video_log(video_log_id)
        except Exception as e:
            messagebox.showerror("错误", f"读取数据库失败: {e}")
            return

        if not materials:
            messagebox.showinfo("提示", f"视频日志 #{video_log_id} 没有素材记录")
            return

        # 创建反馈窗口
        win = tk.Toplevel(self.root)
        win.title(f"素材反馈 - 视频 #{video_log_id}")
        win.geometry("1000x600")
        win.configure(bg="#e8f5e9")

        # 顶部信息栏
        info_frame = tb.Frame(win, padding=8)
        info_frame.pack(fill="x")
        kw = video_log.get("keyword", "")
        ctime = video_log.get("created_at", "")
        tts_dur = video_log.get("tts_duration", 0)
        tb.Label(info_frame, text=f"关键词: {kw}  |  创建时间: {ctime}  |  配音时长: {tts_dur:.1f}s",
                font=("Microsoft YaHei", 10), background="#e8f5e9").pack(anchor="w")

        # 素材列表 Treeview
        tree_frame = tb.Frame(win, padding=4)
        tree_frame.pack(fill="both", expand=True)

        columns = ("#", "path", "start", "duration", "method", "score",
                   "repeat_rating", "fit_rating", "adapt_rating")
        tree = tb.Treeview(tree_frame, columns=columns, show="headings", height=12)
        tree.heading("#", text="#"); tree.column("#", width=35, anchor="center")
        tree.heading("path", text="素材路径"); tree.column("path", width=320)
        tree.heading("start", text="起始(s)"); tree.column("start", width=60, anchor="center")
        tree.heading("duration", text="时长(s)"); tree.column("duration", width=60, anchor="center")
        tree.heading("method", text="匹配方式"); tree.column("method", width=90, anchor="center")
        tree.heading("score", text="匹配分"); tree.column("score", width=60, anchor="center")
        tree.heading("repeat_rating", text="重复率(1-5)"); tree.column("repeat_rating", width=90, anchor="center")
        tree.heading("fit_rating", text="合理性(1-5)"); tree.column("fit_rating", width=90, anchor="center")
        tree.heading("adapt_rating", text="适配率(1-5)"); tree.column("adapt_rating", width=90, anchor="center")
        tree.pack(side="left", fill="both", expand=True)

        scrollbar = tb.Scrollbar(tree_frame, orient="vertical", command=tree.yview, bootstyle="round")
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)

        # 星级下拉选项
        rating_options = ["1", "2", "3", "4", "5"]

        # 存储每个素材的评分变量
        rating_vars = {}

        for i, m in enumerate(materials):
            mid = m["id"]
            path_str = m["material_path"]
            if len(path_str) > 55:
                path_str = "..." + path_str[-52:]

            # 获取该素材已有的反馈
            existing_stats = {}
            try:
                from core.database import db
                existing_stats = db.get_material_feedback_stats(m["material_path"])
            except Exception:
                pass
            avg_str = f" (均{existing_stats.get('avg_rating',0):.1f})" if existing_stats.get("count", 0) > 0 else ""

            repeat_var = tk.StringVar(value="3")
            fit_var = tk.StringVar(value="3")
            adapt_var = tk.StringVar(value="3")
            rating_vars[mid] = {
                "path": m["material_path"],
                "repeat": repeat_var,
                "fit": fit_var,
                "adapt": adapt_var
            }

            tree.insert("", "end", iid=str(mid), values=(
                m["order_index"] + 1,
                path_str,
                f"{m['source_start']:.1f}",
                f"{m['clip_duration']:.1f}",
                m.get("match_method", ""),
                f"{m.get('match_score', 0):.2f}{avg_str}",
                "3", "3", "3"
            ))

        # 点击评分列弹出下拉菜单
        def _on_tree_click(event):
            region = tree.identify_region(event.x, event.y)
            if region != "cell":
                return
            column = tree.identify_column(event.x)
            col_num = int(column.replace("#", ""))
            if col_num not in (7, 8, 9):
                return
            row_id = tree.identify_row(event.y)
            if not row_id or row_id not in rating_vars:
                return

            var_keys = {7: "repeat", 8: "fit", 9: "adapt"}
            var_key = var_keys[col_num]

            bbox = tree.bbox(row_id, column)
            if not bbox:
                return
            x, y, w_cell, h_cell = bbox

            combo = tb.Combobox(tree, values=rating_options, state="readonly",
                               width=8, font=("Microsoft YaHei", 9))
            combo.place(x=x, y=y, width=w_cell, height=h_cell)
            combo.set(rating_vars[row_id][var_key].get())

            def _on_select(evt, rid=row_id, vk=var_key, ci=col_num):
                val = combo.get()
                rating_vars[rid][vk].set(val)
                values_list = list(tree.item(rid, "values"))
                values_list[ci - 1] = val
                tree.item(rid, values=values_list)
                combo.destroy()

            combo.bind("<<ComboboxSelected>>", _on_select)
            combo.bind("<FocusOut>", lambda evt: combo.destroy())
            combo.focus_set()

        tree.bind("<Button-1>", _on_tree_click)

        # 按钮区域
        btn_frame = tb.Frame(win, padding=8)
        btn_frame.pack(fill="x")

        def _submit_feedback():
            """提交所有素材的反馈"""
            try:
                from core.database import db
                count = 0
                for mid, vars_dict in rating_vars.items():
                    path = vars_dict["path"]
                    for fb_type, var_key in [("重复率", "repeat"), ("选取合理率", "fit"), ("适配率", "adapt")]:
                        rating = int(vars_dict[var_key].get())
                        if rating != 3:
                            db.insert_material_feedback(path, video_log_id, fb_type, rating)
                            count += 1
                    r_vals = [int(vars_dict[k].get()) for k in ("repeat", "fit", "adapt")]
                    if all(v == 3 for v in r_vals):
                        db.insert_material_feedback(path, video_log_id, "适配率", 3)
                        count += 1
                messagebox.showinfo("完成", f"已提交 {count} 条反馈记录\n反馈将在后续生成中自动影响素材选取权重")
                win.destroy()
            except Exception as e:
                messagebox.showerror("错误", f"提交失败: {e}")

        RoundedButton(btn_frame, text="提交反馈 / Submit", command=_submit_feedback,
                     width=180, height=38, bg_color="#0d6efd", fg_color="#ffffff",
                     hover_color="#0b5ed7", radius=12).pack(side="left", padx=4)
        RoundedButton(btn_frame, text="取消 / Cancel", command=win.destroy,
                     width=120, height=38, bg_color="#e0e0e0", fg_color="#212529",
                     hover_color="#d0e0ff", radius=12).pack(side="left", padx=4)

        tb.Label(btn_frame, text="点击评分列可下拉选择 1-5 分（1=差, 5=优秀）",
                font=("Microsoft YaHei", 9), foreground="#6d6d6d",
                background="#e8f5e9").pack(side="right", padx=10)

    # ═══════════════ 系统功能 ═══════════════
    # ═══════════════ TAB 7: 脚本学习库 ═══════════════
    def _build_script_lib(self):
        t = tb.Frame(self.nb, padding=10)
        self.nb.add(t, text="脚本学习库 / Script Lib")

        # ── 上部: 添加脚本 ──
        add_frame = tb.Labelframe(t, text="添加脚本", padding=6)
        add_frame.pack(fill="x", pady=4)

        self.slib_input = tk.Text(add_frame, font=("Microsoft YaHei", 11),
                                   bg="#ffffff", fg="#1b5e20")
        self.slib_input.pack(fill="x", pady=2)

        row1 = tb.Frame(add_frame); row1.pack(fill="x")
        tb.Label(row1, text="标签:").pack(side="left")
        self.slib_tags_var = tk.StringVar()
        tk.Entry(row1, textvariable=self.slib_tags_var, width=30,
                bg="#ffffff", fg="#1b5e20").pack(side="left", padx=4)

        self.slib_force_line = tk.BooleanVar(value=False)
        tb.Checkbutton(row1, text="强制按行", variable=self.slib_force_line
                       ).pack(side="left", padx=4)
        RoundedButton(row1, text="智能导入", command=self._slib_smart_add, width=100, height=34, bg_color="#0d6efd", fg_color="#ffffff", hover_color="#0b5ed7", radius=10).pack(side="left", padx=4)
        RoundedButton(row1, text="从文件导入", command=self._slib_import, width=100, height=34, bg_color="#0d6efd", fg_color="#ffffff", hover_color="#0b5ed7", radius=10).pack(side="left", padx=4)
        self.slib_status = tb.Label(row1, text="", foreground="#4a7c4f")
        self.slib_status.pack(side="left", padx=10)

        # ── 中部: 脚本列表 ──
        list_frame = tb.Labelframe(t, text="脚本列表", padding=4)
        list_frame.pack(fill="both", expand=True, pady=4)

        bf = tb.Frame(list_frame); bf.pack(fill="x")
        RoundedButton(bf, text="刷新", command=self._slib_refresh, width=110, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="left", padx=2)
        self.slib_search_var = tk.StringVar()
        tk.Entry(bf, textvariable=self.slib_search_var, width=20,
                bg="#ffffff", fg="#1b5e20").pack(side="left", padx=4)
        RoundedButton(bf, text="搜索", command=self._slib_search, width=110, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="left", padx=2)
        RoundedButton(bf, text="删除选中", command=self._slib_delete, width=110, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="right", padx=2)
        RoundedButton(bf, text="使用选中", command=self._slib_use, width=110, height=34, bg_color="#e0e0e0", fg_color="#212529", hover_color="#d0e0ff", radius=10).pack(side="right", padx=2)

        self.slib_tree = tb.Treeview(list_frame,
            columns=("id","preview","tags","count","score","last"),
            show="headings")
        self.slib_tree.heading("id", text="ID")
        self.slib_tree.column("id", width=40, anchor="center")
        self.slib_tree.heading("preview", text="脚本预览")
        self.slib_tree.column("preview", width=480)
        self.slib_tree.heading("tags", text="标签")
        self.slib_tree.column("tags", width=110)
        self.slib_tree.heading("count", text="次数")
        self.slib_tree.column("count", width=55, anchor="center")
        self.slib_tree.heading("score", text="评分")
        self.slib_tree.column("score", width=55, anchor="center")
        self.slib_tree.heading("last", text="最后使用")
        self.slib_tree.column("last", width=110)
        self.slib_tree.pack(fill="both", expand=True)

        self.slib_tree.bind("<Double-1>", lambda e: self._slib_edit())

        # ── 下部: 详情 ──
        det_frame = tb.Labelframe(t, text="脚本详情与分析", padding=4)
        det_frame.pack(fill="x", pady=4)

        self.slib_detail = tk.Text(det_frame, font=("Microsoft YaHei", 10),
                                    bg="#c8e6c9", fg="#1b5e20", state="disabled")
        self.slib_detail.pack(fill="x")

        # 初始加载
        self._slib_refresh()

    def _slib_smart_add(self):
        """智能导入：自动分割粘贴区中的多个脚本"""
        raw_text = self.slib_input.get("1.0", "end-1c").strip()
        if not raw_text:
            messagebox.showinfo("提示", "请粘贴脚本内容")
            return
        tags = [t.strip() for t in self.slib_tags_var.get().split(",") if t.strip()]
        try:
            from core.script_learning import get_library
            lib = get_library()
            result = lib.import_scripts_from_text(
                raw_text, source="manual",
                force_by_line=self.slib_force_line.get(),
                skip_duplicates=True)
            self._slib_refresh()
            self.slib_input.delete("1.0", "end")
            self.slib_tags_var.set("")
            self.slib_status.config(
                text=f"[OK] 新增 {result['added']}, 跳过 {result['skipped']}",
                foreground="#43a047")
        except Exception as e:
            self.slib_status.config(text=f"导入失败: {e}", foreground="#e53935")

    def _slib_import(self):
        from tkinter import filedialog, messagebox
        path = filedialog.askopenfilename(
            title="选择脚本文件", filetypes=[("Excel/Text files","*.xlsx *.txt")])
        if not path:
            return

        self.slib_status.config(text="正在导入...", foreground="#ffb74d")
        self.root.update_idletasks()

        try:
            raw_text = ""
            if path.endswith(".xlsx"):
                try:
                    import openpyxl
                except ImportError:
                    messagebox.showerror("缺少依赖",
                        "请先安装 openpyxl：\npip install openpyxl")
                    self.slib_status.config(text="导入失败: 缺少 openpyxl", foreground="#e53935")
                    return

                wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
                ws = wb.active
                cell_texts = []
                for row in ws.iter_rows(values_only=True):
                    for cell in row:
                        if cell is not None and str(cell).strip():
                            cell_texts.append(str(cell).strip())
                wb.close()
                raw_text = "\n\n".join(cell_texts)
                if not raw_text.strip():
                    messagebox.showinfo("提示", "Excel 文件中没有检测到文本内容")
                    self.slib_status.config(text="文件为空", foreground="#e53935")
                    return
            else:
                with open(path, encoding="utf-8") as _f: raw_text = _f.read()

            if not raw_text.strip():
                messagebox.showinfo("提示", "文件中没有检测到任何文本内容")
                self.slib_status.config(text="导入失败: 文件为空", foreground="#e53935")
                return

            from core.script_learning import get_library
            lib = get_library()
            result = lib.import_scripts_from_text(
                raw_text, source="file",
                force_by_line=self.slib_force_line.get(),
                skip_duplicates=True)

            self._slib_refresh()
            self.slib_status.config(
                text=f"[OK] 新增 {result['added']}, 跳过 {result['skipped']}",
                foreground="#43a047")
            messagebox.showinfo("导入完成",
                f"成功导入 {result['added']} 条脚本\n跳过 {result['skipped']} 条重复")

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.slib_status.config(text=f"导入失败: {str(e)[:50]}", foreground="#e53935")
            messagebox.showerror("导入错误", f"文件解析失败:\n{str(e)}")

    def _slib_refresh(self):
        self.slib_tree.delete(*self.slib_tree.get_children())
        try:
            from core.script_learning import get_library
            lib = get_library()
            scripts = lib.get_all(limit=100)
            for s in scripts:
                preview = s["content"][:200].replace("\n", " ")
                self.slib_tree.insert("", "end",
                    values=(s["id"], preview, s.get("tags","")[:30],
                            s.get("usage_count",0), s.get("avg_score",0),
                            (s.get("last_used_at","") or "")[:10]),
                    tags=(str(s["id"]),))
            self.slib_status.config(
                text=f"{len(scripts)} 条脚本", foreground="#4a7c4f")
        except Exception as e:
            self.slib_status.config(text=f"加载失败: {e}", foreground="#e53935")

    def _slib_search(self):
        q = self.slib_search_var.get().strip()
        if not q:
            self._slib_refresh()
            return
        self.slib_tree.delete(*self.slib_tree.get_children())
        try:
            from core.script_learning import get_library
            for s in get_library().search(q, limit=50):
                preview = s["content"][:200].replace("\n", " ")
                self.slib_tree.insert("", "end",
                    values=(s["id"], preview, s.get("tags","")[:30],
                            s.get("usage_count",0), s.get("avg_score",0),
                            (s.get("last_used_at","") or "")[:10]),
                    tags=(str(s["id"]),))
        except Exception as e:
            self.slib_status.config(text=f"搜索失败: {e}", foreground="#e53935")

    def _slib_delete(self):
        sel = self.slib_tree.selection()
        if not sel:
            return
        if messagebox.askyesno("确认", f"删除选中的 {len(sel)} 条脚本?"):
            from core.script_learning import get_library
            for item in sel:
                sid = int(self.slib_tree.item(item, "tags")[0])
                get_library().delete(sid)
            self._slib_refresh()

    def _slib_use(self):
        sel = self.slib_tree.selection()
        if not sel:
            return
        sid = int(self.slib_tree.item(sel[0], "tags")[0])
        from core.script_learning import get_library
        s = get_library().get_by_id(sid)
        if s:
            # 切换到快速生成 Tab 并填入脚本
            self.nb.select(0)
            self.copy_text.delete("1.0", "end")
            self.copy_text.insert("1.0", s["content"])
            self.kw_entry.set("脚本学习库")
            self._set_status(f"已加载脚本 #{sid}")

    def _slib_edit(self):
        sel = self.slib_tree.selection()
        if not sel:
            return
        sid = int(self.slib_tree.item(sel[0], "tags")[0])
        from core.script_learning import get_library
        s = get_library().get_by_id(sid)
        if not s:
            return
        # 显示详情
        self.slib_detail.config(state="normal")
        self.slib_detail.delete("1.0", "end")
        self.slib_detail.insert("1.0",
            f"ID: {s['id']} | 来源: {s.get('source','?')} | 使用: {s.get('usage_count',0)}次 | 评分: {s.get('avg_score',0):.1f}\n"
            f"标签: {s.get('tags','')}\n"
            f"创建: {s.get('created_at','')} | 最后使用: {s.get('last_used_at','')}\n"
            f"──\n{s['content']}")
        self.slib_detail.config(state="disabled")

        # 找相似脚本
        try:
            similar = get_library().find_similar(s["content"], top_k=3)
            if similar:
                self.slib_detail.config(state="normal")
                self.slib_detail.insert("end", "\n\n── 相似脚本推荐 ──\n")
                for sim in similar:
                    self.slib_detail.insert("end",
                        f"  [{sim['similarity']:.2f}] #{sim['id']}: {sim['content'][:50]}...\n")
                self.slib_detail.config(state="disabled")
        except Exception:
            pass

    # ═══════════════════ 系统功能 ═══════════════════
    def _show_help(self):
        from ui.help_window import show_help
        show_help(self.root)

    def _auto_detect_video_folders(self):
        """首次运行时自动扫描盘符找到包含视频的文件夹"""
        from core.drive_scanner import get_scanner
        try:
            scanner = get_scanner()
            drives = scanner.get_drives()
            candidates = []
            for drive in drives[:3]:  # 只扫描前3个盘符
                try:
                    for item in os.scandir(drive):
                        if item.is_dir() and not item.name.startswith((".", "$", "Windows", "Program")):
                            has_video = False
                            try:
                                for sub in os.scandir(item.path):
                                    if sub.is_file() and sub.name.lower().endswith((".mp4", ".mov", ".avi")):
                                        has_video = True
                                        break
                            except Exception:
                                pass
                            if has_video:
                                candidates.append(item.path)
                                if len(candidates) >= 5:
                                    break
                except Exception:
                    continue
                if len(candidates) >= 5:
                    break
            if candidates:
                self._log(f"[AutoDetect] 发现 {len(candidates)} 个候选文件夹")
        except Exception:
            pass

    def _on_nb_tab_change(self, event=None):
        """Auto-load content when tab is selected"""
        try:
            tab = self.nb.tab(self.nb.select(), "text")
            if tab and "素材盘检索" in str(tab) and hasattr(self, 'disk_vids'):
                self._on_refresh_lib()
            if tab and "历史" in str(tab) and hasattr(self, 'hist_tree'):
                self._load_hist()
        except Exception:
            pass

    def _warmup(self):
        try: _get_folders_fast(); self._cache_ready = True
        except Exception as _e: from utils.logging import log_warning; log_warning('desktop', str(_e)[:80])
        try: _get_ve(); self._ve_ready = True
        except Exception as _e: from utils.logging import log_warning; log_warning('desktop', str(_e)[:80])
        # ★ v12.0: 后台接線EventBus
        try:
            from core.event_wiring import wire_all
            wire_all()
        except Exception:
            pass

    # ═══════════════ ★ v12.0 審核面板Tab ═══════════════
    def _build_review_tab(self):
        """AI審核面板 — 人工審核AI建議"""
        t = tb.Frame(self.nb, padding=8)
        self.nb.add(t, text="🔍 審核 Review")

        try:
            from ui.review_panel import ReviewPanel
            self._review_panel = ReviewPanel(t)
            self._review_panel.pack(fill="both", expand=True)
        except ImportError:
            tb.Label(t, text="審核面板模塊未載入\n請確認 core/review_queue.py 正常",
                     font=("Microsoft YaHei", 11), foreground="gray").pack(pady=30)

    # ═══════════════ ★ v12.0 統一日誌窗口Tab ═══════════════
    def _build_logs_tab(self):
        """統一日誌窗口 — EventBus LOG_MESSAGE 訂閱顯示"""
        t = tb.Frame(self.nb, padding=6)
        self.nb.add(t, text="📋 日誌 Logs")

        # Toolbar
        tb_frame = tb.Frame(t)
        tb_frame.pack(fill="x", pady=(0, 4))
        tb.Label(tb_frame, text="即時日誌", font=("Microsoft YaHei", 11, "bold")).pack(side="left")
        tb.Button(tb_frame, text="清除", bootstyle="outline-secondary", command=self._clear_logs).pack(side="right", padx=4)

        self._logs_text = scrolledtext.ScrolledText(
            t, font=("Consolas", 9), bg="#1a1a2e", fg="#00ff88",
            insertbackground="#00ff88", height=20, wrap="word"
        )
        self._logs_text.pack(fill="both", expand=True)
        self._logs_text.insert("end", "=== TreeCut v12.0 日誌系統已啟動 ===\n")
        self._logs_text.insert("end", "等待事件...\n\n")
        self._logs_text.see("end")

        self._max_log_lines = 5000  # 限制行數防止內存溢出

    def _clear_logs(self):
        if hasattr(self, '_logs_text'):
            self._logs_text.delete("1.0", "end")
            self._logs_text.insert("end", "=== 日誌已清除 ===\n\n")

    def _append_log(self, level: str, msg: str, module: str = ""):
        """向統一日誌窗口追加消息 (線程安全)"""
        def _do():
            if not hasattr(self, '_logs_text'):
                return
            color = {"ERROR": "#ff4444", "WARNING": "#ffaa00", "INFO": "#44aaff", "DEBUG": "#888888"}.get(level, "#ffffff")
            self._logs_text.insert("end", f"[{module}|{level}] {msg}\n", level)
            self._logs_text.tag_config(level, foreground=color)
            # 限制行數
            lines = int(self._logs_text.index("end-1c").split(".")[0])
            if lines > self._max_log_lines:
                self._logs_text.delete("1.0", f"{lines - self._max_log_lines}.0")
            self._logs_text.see("end")
        self.root.after(0, _do)

    def _subscribe_events(self):
        """★ v12.0: 訂閱EventBus事件 — UI自動響應後台狀態"""
        try:
            from core.event_bus import get_bus, Events
            bus = get_bus()

            bus.subscribe(Events.LOG_MESSAGE,
                lambda d: self._append_log(d.get("level","INFO"), d.get("message",""), d.get("module","?"))
                if d else None)

            bus.subscribe(Events.GENERATION_DONE,
                lambda d: self._set_status(f"✅ 生成完成: {d.get('keyword','?')}" if d else "✅ 完成"))

            bus.subscribe(Events.GENERATION_FAILED,
                lambda d: self._set_status(f"❌ 生成失敗: {d.get('error','?')[:40]}" if d else "❌ 失敗"))

            bus.subscribe(Events.PROGRESS_UPDATE,
                lambda d: self._set_status(f"⏳ {d.get('done',0)}/{d.get('total',1)}" if d else "⏳"))

            bus.subscribe(Events.REVIEW_PENDING,
                lambda d: self._update_review_badge(d.get("count",0) if d else 0))
        except ImportError:
            pass
        except Exception:
            pass

    def _update_review_badge(self, count: int):
        """更新審核Tab紅點提示"""
        def _do():
            try:
                tab_text = f"🔍 審核({count})" if count > 0 else "🔍 審核 Review"
                # 遍歷notebook更新tab文本
                for i in range(self.nb.index("end")):
                    if "審核" in str(self.nb.tab(i, "text")):
                        self.nb.tab(i, text=tab_text)
                        break
            except Exception:
                pass
        self.root.after(0, _do)

    def _on_system_status(self):
        try:
            from core.library_builder import LibraryBuilder
            s = LibraryBuilder().get_stats()
            msg = f"素材片段: {s['total_segments']:,}\n已分析: {s['analyzed_videos']:,}\n总视频: {s['total_videos']:,}"
            messagebox.showinfo("系统状态", msg)
        except Exception as e: messagebox.showerror("错误", str(e))

    def _on_review(self):
        try:
            from review_audit import AuditEngine
            self._set_status("审查中...")
            def _r():
                e = AuditEngine(); e.run_full(); s = e.compute_score()
                self.root.after(0, lambda: messagebox.showinfo("复查", f"评分: {s['score']}/100 ({s['grade']}级)"))
            threading.Thread(target=_r, daemon=True).start()
        except Exception as e: messagebox.showerror("错误", str(e))

    def _on_clear_all_cache(self):
        if messagebox.askyesno("确认","清除所有缓存?"):
            global _folder_cache
            with _cache_lock: _folder_cache = None
            (Path(__file__).parent.parent / "folder_cache.json").unlink(missing_ok=True)
            try: _get_ve().MaterialCacheManager.invalidate()
            except Exception as _e: from utils.logging import log_warning; log_warning('desktop', str(_e)[:80])
            self._log("缓存已清除")

    def _on_settings(self):
        from ui.settings_page import SettingsPage; SettingsPage(self)

    def _on_scan_all(self):
        """全盘素材扫描 → 切换到素材盘检索的学习日志面板 (v11.4)"""
        self.nb.select(1)  # 切换到素材盘检索标签页
        if hasattr(self, '_panel_learn'):
            try:
                self._switch_material_panel(self._panel_learn)
            except Exception:
                pass
        self._set_status("学习日志/后台扫描面板已就绪")

    # 注意: _on_check_ollama / _on_download_model 已移除 — 视觉模型已强制使用本地 Qwen3-VL-4B

    # ═══════════════ TAB 8: 素材学习日志 ═══════════════

    def run(self): self.root.mainloop()

if __name__ == "__main__":
    TreeCutApp().run()
