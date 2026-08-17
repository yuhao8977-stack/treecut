"""
树剪 — 素材标注 Tab v5.0 (批量识别 + 放大显示 + 布局优化 + 自动加载DB帧)
=================================================================
布局: 左侧35%视频列表 | 右侧65%关键帧滚动区域
功能: 自动批量识别 / 放大帧卡片 (240x180) / DB已有帧自动加载 / 标签编辑+打分
"""
import os, sys, json, time, threading, io, queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

sys.path.insert(0, str(Path(__file__).parent.parent))
from ui.rounded_button import RoundedButton
from core.smart_match_engine import script_hash as make_script_hash


class FrameAnnotationTab:
    """帧级标注标签页 v5.0"""

    def __init__(self, notebook, app):
        self.app = app
        self.tab = ttk.Frame(notebook)
        notebook.add(self.tab, text="帧级标注")
        self._annotator = None
        self._analyzing = False
        self._batch_running = False
        self._batch_cancel = threading.Event()
        self._current_video = None
        self._fw = []  # frame widget references
        self._frame_idx_map = {}
        self._current_folder = None  # 当前加载的文件夹路径
        self._video_paths = []  # 当前文件夹下的所有视频路径列表
        self._build()
        # v11.4: 注册数据库变更回调
        try:
            from core.database import db
            db.register_callback(self._on_db_data_changed)
        except Exception:
            pass

    def _build(self):
        paned = ttk.PanedWindow(self.tab, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=4, pady=4)

        # ═══════ LEFT: 驱动器树(紧凑) + 视频列表 (35%) ═══════
        left = ttk.Frame(paned, width=320)
        paned.add(left, weight=1)
        left.pack_propagate(False)

        # 驱动器/文件夹选择
        drive_lf = ttk.LabelFrame(left, text="素材源", padding=2)
        drive_lf.pack(fill="x", pady=(0, 2))
        btn_row = ttk.Frame(drive_lf); btn_row.pack(fill="x")
        RoundedButton(btn_row, text="扫描驱动器", command=self._on_scan,
                     height=30, bg_color="#e0e0e0", fg_color="#212529",
                     hover_color="#d0e0ff", radius=8).pack(side="left", padx=1, fill="x", expand=True)
        RoundedButton(btn_row, text="选文件夹", command=self._on_browse,
                     height=30, bg_color="#e0e0e0", fg_color="#212529",
                     hover_color="#d0e0ff", radius=8).pack(side="left", padx=1, fill="x", expand=True)
        self._drive_tree = ttk.Treeview(drive_lf, show="tree", height=5)
        self._drive_tree.pack(fill="x", pady=2)
        self._drive_tree.bind("<<TreeviewSelect>>", self._on_drive_select)
        self._drive_tree.bind("<Double-1>", self._on_drive_double)

        # 视频列表
        video_lf = ttk.LabelFrame(left, text="视频列表", padding=2)
        video_lf.pack(fill="both", expand=True, pady=(2, 0))
        self._video_tree = ttk.Treeview(video_lf,
            columns=("name", "size", "dur"), show="headings", height=10)
        self._video_tree.heading("name", text="文件名"); self._video_tree.column("name", width=300, minwidth=150)
        self._video_tree.heading("size", text="大小"); self._video_tree.column("size", width=70, anchor="center", minwidth=50)
        self._video_tree.heading("dur", text="时长"); self._video_tree.column("dur", width=65, anchor="center", minwidth=50)
        self._video_tree.pack(fill="both", expand=True)
        self._video_tree.bind("<<TreeviewSelect>>", self._on_video_select)
        self._video_tree.bind("<Double-1>", lambda e: self._recognize_current())

        # ═══════ RIGHT: 帧展示区 (65%) ═══════
        right = ttk.Frame(paned, width=680)
        paned.add(right, weight=3)

        # 控制按钮行
        ctrl_frame = ttk.LabelFrame(right, text="识别控制", padding=4)
        ctrl_frame.pack(fill="x", pady=(0, 4))

        ctrl_row1 = ttk.Frame(ctrl_frame); ctrl_row1.pack(fill="x")
        RoundedButton(ctrl_row1, text="启动全帧识别（当前视频）", command=self._recognize_current,
                     height=34, bg_color="#0d6efd", fg_color="#ffffff",
                     hover_color="#0b5ed7", radius=8).pack(side="left", padx=2)
        RoundedButton(ctrl_row1, text="自动批量识别（所有视频）", command=self._batch_recognize_all,
                     height=34, bg_color="#28a745", fg_color="#ffffff",
                     hover_color="#218838", radius=8).pack(side="left", padx=2)
        RoundedButton(ctrl_row1, text="预览视频", command=self._on_preview,
                     height=34, bg_color="#e0e0e0", fg_color="#212529",
                     hover_color="#d0e0ff", radius=8).pack(side="left", padx=2)
        RoundedButton(ctrl_row1, text="取消", command=self._on_cancel,
                     height=34, bg_color="#dc3545", fg_color="#ffffff",
                     hover_color="#c82333", radius=8).pack(side="left", padx=2)
        self._batch_stop_btn = RoundedButton(ctrl_row1, text="停止批量", command=self._stop_batch,
                     height=34, bg_color="#fd7e14", fg_color="#ffffff",
                     hover_color="#e06a00", radius=8)
        self._batch_stop_btn.pack(side="left", padx=2)
        self._batch_stop_btn.configure(state="disabled")

        ctrl_row2 = ttk.Frame(ctrl_frame); ctrl_row2.pack(fill="x", pady=(3, 0))
        self._status_lbl = ttk.Label(ctrl_row2, text="就绪 — 从左侧选择视频",
                                     foreground="#888", font=("Microsoft YaHei", 9))
        self._status_lbl.pack(side="left", padx=4)
        self._progress = ttk.Progressbar(ctrl_row2, mode="determinate", length=180)
        self._progress.pack(side="right", padx=4)
        self._pg_lbl = ttk.Label(ctrl_row2, text="", width=8, font=("Microsoft YaHei", 9))
        self._pg_lbl.pack(side="right")

        # 关键帧滚动区域 — 放大
        ff = ttk.LabelFrame(right, text="关键帧 / Frames", padding=4)
        ff.pack(fill="both", expand=True, pady=2)
        self._frame_canvas = tk.Canvas(ff, bg="#e8f5e9", highlightthickness=0)
        self._frame_scroll = ttk.Scrollbar(ff, orient="vertical",
                                           command=self._frame_canvas.yview)
        self._frame_inner = ttk.Frame(self._frame_canvas)
        self._frame_inner.bind("<Configure>", lambda e: self._frame_canvas.configure(
            scrollregion=self._frame_canvas.bbox("all")))
        # 内部框架宽度放大到 980 以适应每行 3 个 280px 卡片
        self._frame_canvas.create_window((0, 0), window=self._frame_inner,
                                         anchor="nw", width=960)
        self._frame_canvas.configure(yscrollcommand=self._frame_scroll.set)
        self._frame_canvas.pack(side="left", fill="both", expand=True)
        self._frame_scroll.pack(side="right", fill="y")
        self._frame_canvas.bind("<MouseWheel>",
            lambda e: self._frame_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # 批量识别实时日志
        log_frame = ttk.LabelFrame(right, text="批量识别日志", padding=2)
        log_frame.pack(fill="x", pady=(4, 0))
        self._batch_log = tk.Text(log_frame, font=("Consolas", 9),
                                  height=4, bg="#1b1b1b", fg="#a5d6a7",
                                  state="disabled", wrap="word")
        self._batch_log.pack(fill="x")
        batch_log_scroll = ttk.Scrollbar(log_frame, orient="vertical",
                                         command=self._batch_log.yview)
        batch_log_scroll.pack(side="right", fill="y")
        self._batch_log.configure(yscrollcommand=batch_log_scroll.set)

        # 底部操作栏
        btm = ttk.LabelFrame(right, text="操作 / Actions", padding=4)
        btm.pack(fill="x", pady=(4, 0))
        RoundedButton(btm, text="全选", command=lambda: self._sel_all(True),
                     height=34, bg_color="#e0e0e0", fg_color="#212529",
                     hover_color="#d0e0ff", radius=8).pack(side="left", padx=2)
        RoundedButton(btm, text="取消全选", command=lambda: self._sel_all(False),
                     height=34, bg_color="#e0e0e0", fg_color="#212529",
                     hover_color="#d0e0ff", radius=8).pack(side="left", padx=2)
        RoundedButton(btm, text="批量修改标签", command=self._batch_edit,
                     height=34, bg_color="#e0e0e0", fg_color="#212529",
                     hover_color="#d0e0ff", radius=8).pack(side="left", padx=2)
        RoundedButton(btm, text="提交反馈+学习", command=self._on_feedback,
                     height=34, bg_color="#0d6efd", fg_color="#ffffff",
                     hover_color="#0b5ed7", radius=8).pack(side="left", padx=2)
        self._sel_lbl = ttk.Label(btm, text="已选:0", foreground="#888",
                                  font=("Microsoft YaHei", 9))
        self._sel_lbl.pack(side="left", padx=10)
        self._fb_lbl = ttk.Label(btm, text="", foreground="#43a047",
                                 font=("Microsoft YaHei", 9))
        self._fb_lbl.pack(side="left", padx=10)

        sf = ttk.Frame(right); sf.pack(fill="x", pady=2)
        self._stats_lbl = ttk.Label(sf, text="", foreground="#888",
                                    font=("Microsoft YaHei", 9))
        self._stats_lbl.pack(side="left")
        self._refresh_stats()

    # ═══════════════════════════════════════════════════════════
    # 驱动器树
    # ═══════════════════════════════════════════════════════════
    def _on_scan(self):
        self._drive_tree.delete(*self._drive_tree.get_children())
        self._status_lbl.config(text="扫描中...")
        def _run():
            try:
                from core.drive_scanner import get_scanner
                s = get_scanner()
                self.app.root.after(0, lambda: self._status_lbl.config(text="扫描全盘..."))
                drive_entries = s.get_quick_scan()
                from core.config import SELLING_POINT_DIR, EFFECTS_DIR, B_GROUP_PATH
                extra_roots = []
                for sp in [SELLING_POINT_DIR, EFFECTS_DIR, B_GROUP_PATH]:
                    if os.path.exists(sp):
                        root_entry = s.scan_folder(sp, max_depth=1)
                        extra_roots.append(root_entry)
                self.app.root.after(0, lambda: self._populate_drives(drive_entries, extra_roots))
            except Exception as e:
                self.app.root.after(0, lambda: self._status_lbl.config(text=f"扫描失败:{e}"))
        threading.Thread(target=_run, daemon=True).start()

    def _populate_drives(self, drive_entries, extra_roots=None):
        self._drive_tree.delete(*self._drive_tree.get_children())
        total_folders = 0
        for e in drive_entries:
            self._drive_tree.insert("", "end",
                text=f"[DRIVE] {e.name} ({e.video_count}视频)" if e.is_drive else f"[DIR] {e.name} ({e.video_count}视频)",
                open=False, values=(e.path,))
            total_folders += 1
        if extra_roots:
            for root in extra_roots:
                pnode = self._drive_tree.insert("", "end",
                    text=f"[ROOT] {root.name} ({root.video_count}视频)",
                    open=True, values=(root.path,))
                total_folders += 1
                for child in root.children:
                    if child.video_count > 0:
                        self._drive_tree.insert(pnode, "end",
                            text=f"[DIR] {child.name} ({child.video_count})",
                            values=(child.path,))
                        total_folders += 1
        self._status_lbl.config(text=f"就绪 — {total_folders}个文件夹")

    def _on_browse(self):
        from tkinter import filedialog
        p = filedialog.askdirectory(title="选择文件夹")
        if p:
            self._current_video = None
            self._current_folder = p
            self._load_videos(p)

    def _on_drive_select(self, ev):
        sel = self._drive_tree.selection()
        if sel:
            vals = self._drive_tree.item(sel[0], "values")
            if vals:
                self._current_folder = vals[0]
                self._load_videos(vals[0])

    def _on_drive_double(self, ev):
        sel = self._drive_tree.selection()
        if sel:
            vals = self._drive_tree.item(sel[0], "values")
            if vals:
                self._current_folder = vals[0]
                self._load_videos(vals[0])
                try:
                    from core.drive_scanner import get_scanner
                    s = get_scanner()
                    entry = s.scan_folder(vals[0], max_depth=2)
                    self._drive_tree.delete(sel[0])
                    new_node = self._drive_tree.insert("", "end",
                        text=f"[DIR] {entry.name} ({entry.video_count}视频)",
                        open=True, values=(entry.path,))
                    for child in entry.children:
                        if child.video_count > 0:
                            self._drive_tree.insert(new_node, "end",
                                text=f"[DIR] {child.name} ({child.video_count})",
                                values=(child.path,))
                except Exception:
                    pass

    # ═══════════════════════════════════════════════════════════
    # 视频列表加载
    # ═══════════════════════════════════════════════════════════
    def _load_videos(self, folder):
        self._video_tree.delete(*self._video_tree.get_children())
        self._video_paths = []
        self._status_lbl.config(text=f"加载中... {folder[:40]}")
        self._progress["value"] = 0; self._pg_lbl.config(text="")
        self.app.root.update_idletasks()
        if hasattr(self, '_load_cancel'): self._load_cancel.set()
        self._load_cancel = threading.Event()

        def _run():
            try:
                from core.drive_scanner import get_scanner
                scanner = get_scanner()
                vids = scanner.list_videos(folder, probe=False,
                                           cancel_event=self._load_cancel)[:500]
                total = len(vids)
                for v in vids:
                    self._video_paths.append(v.path)
                self.app.root.after(0, lambda: (
                    self._show_videos_fast(vids),
                    self._status_lbl.config(text=f"获取元数据中... 0/{total}"),
                    self._progress.configure(maximum=total)
                ))
                if total > 0:
                    scanner._batch_probe(vids, progress=self._probe_progress,
                                        cancel_event=self._load_cancel)
                self.app.root.after(0, lambda: self._status_lbl.config(
                    text=f"{total}个视频 — 点击选择, 双击识别"))
            except Exception as e:
                self.app.root.after(0, lambda: self._status_lbl.config(text=f"加载失败:{e}"))
        threading.Thread(target=_run, daemon=True).start()

    def _probe_progress(self, done, total, ve):
        self.app.root.after(0, lambda: (
            self._update_video_row(ve),
            self._progress.configure(value=done),
            self._pg_lbl.config(text=f"{done}/{total}"),
            self._status_lbl.config(text=f"分析中... {done}/{total}")
        ))

    def _show_videos_fast(self, vids):
        self._video_tree.delete(*self._video_tree.get_children())
        self._video_paths = []
        for v in vids:
            self._video_paths.append(v.path)
            self._video_tree.insert("", "end",
                values=(v.name[:60], "-", "-"), tags=(v.path,))

    def _update_video_row(self, ve):
        for item in self._video_tree.get_children():
            tags = self._video_tree.item(item, "tags")
            if tags and tags[0] == ve.path:
                self._video_tree.item(item, values=(
                    ve.name[:50], f"{ve.size_mb:.1f}MB", ve.duration_str))
                break

    # ═══════════════════════════════════════════════════════════
    # 视频选中 → 自动加载DB已有帧数据
    # ═══════════════════════════════════════════════════════════
    # ═══════════════════════════════════════════════════════════
    # 视频选中 → 自动加载DB已有帧数据（显示帧卡片）
    # ═══════════════════════════════════════════════════════════
    def _on_video_select(self, ev):
        sel = self._video_tree.selection()
        if not sel:
            return
        tags = self._video_tree.item(sel[0], "tags")
        if not tags:
            return
        vp = tags[0]
        self._current_video = vp
        vname = Path(vp).name
        self._status_lbl.config(text=f"选中: {vname[:50]} — 查询已有帧...")

        # 自动从 DB 加载已有帧
        threading.Thread(target=self._load_frames_from_db,
                        args=(vp,), daemon=True).start()

    def _load_frames_from_db(self, video_path: str):
        """查询 video_frames 表，已有记录则直接显示"""
        try:
            from core.database import db
            rows = db.get_frames_by_video(video_path)
        except Exception as e:
            self.app.root.after(0, lambda: self._status_lbl.config(
                text=f"查询帧数据失败: {e}"))
            return

        if not rows:
            self.app.root.after(0, lambda: self._status_lbl.config(
                text=f"尚未识别 — 点击「启动全帧识别」或「自动批量识别」"))
            # 清空旧帧
            self.app.root.after(0, self._clear_frames)
            return

        self.app.root.after(0, lambda: self._status_lbl.config(
            text=f"已加载 {len(rows)} 帧 (来自数据库)"))
        self.app.root.after(0, lambda: self._show_frames_from_db(rows))

    def _clear_frames(self):
        for w in self._frame_inner.winfo_children():
            w.destroy()
        self._fw = []
        self._frame_idx_map = {}

    def _show_frames_from_db(self, rows: list):
        """根据数据库记录重建帧卡片（无图片仅显示标签）"""
        self._clear_frames()

        col = 0; row_idx = 0
        cards_per_row = 3  # 每行3个卡片

        for i, data in enumerate(rows):
            fid = data.get("id", i)
            ts = data.get("frame_timestamp", 0)
            img_path = data.get("frame_image_path", "")
            caption = data.get("caption", "")
            objects = data.get("objects", "")
            user_score = data.get("user_score", 3)
            user_tags = data.get("user_tags", "")
            scene = data.get("scene_type", "")

            # 组装模型标签
            model_tags = {}
            if objects:
                model_tags["Vision"] = objects.split(", ")
            if caption:
                model_tags["Caption"] = [caption[:50]]

            # 构建卡片
            cfg = {
                "id": fid,
                "idx": i,
                "ts_sec": ts,
                "ts_str": self._fmt_ts(ts),
                "img_path": img_path,
                "model_tags": model_tags,
                "user_tags": user_tags,
                "score": user_score,
                "scene": scene,
            }
            col = i % cards_per_row
            if col == 0 and i > 0:
                row_idx += 1
            self._add_frame_card_from_db(cfg, col, row_idx)

        self._status_lbl.config(text=f"显示 {len(rows)} 帧 | 双击编辑, 勾选批量操作")

    def _add_frame_card_from_db(self, cfg: dict, col: int, row: int):
        """根据数据库记录创建帧卡片"""
        i = cfg["idx"]
        img_path = cfg["img_path"]
        card = tk.Frame(self._frame_inner, bg="#f1f8e9", bd=1, relief="solid",
                       padx=6, pady=6)
        card.grid(row=row, column=col, sticky="nsew", padx=3, pady=3)

        # 帧号 + 时间
        tk.Label(card, text=f"#{i+1} {cfg['ts_str']}", bg="#f1f8e9",
                fg="#2e7d32", font=("Consolas", 10, "bold")).pack(anchor="w")

        # 场景
        if cfg.get("scene"):
            tk.Label(card, text=cfg["scene"][:20], bg="#f1f8e9",
                    fg="#888", font=("Microsoft YaHei", 8)).pack(anchor="w")

        # 缩略图 — 放大到 240x180
        if HAS_PIL and img_path and os.path.exists(img_path):
            try:
                img = Image.open(img_path)
                img.thumbnail((240, 180), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                lbl_img = tk.Label(card, image=photo, bg="#f1f8e9")
                lbl_img.image = photo
                lbl_img.pack(pady=3)
            except Exception:
                tk.Label(card, text="[图片加载失败]", bg="#f1f8e9", fg="#ccc",
                        font=("Microsoft YaHei", 9)).pack(pady=4)
        else:
            tk.Label(card, text="[无图片]", bg="#f1f8e9", fg="#ccc",
                    font=("Microsoft YaHei", 9)).pack(pady=4)

        # 模型标签摘要
        parts = []
        for model, tags in cfg.get("model_tags", {}).items():
            if isinstance(tags, list):
                parts.append(f"{model}: {', '.join(tags[:3])}")
            else:
                parts.append(f"{model}: {tags}")
        tag_str = "\n".join(parts) if parts else "[AI] 无标签"
        tag_text = tk.StringVar(value=tag_str)
        tk.Label(card, textvariable=tag_text, bg="#f1f8e9", fg="#4a7c4f",
                font=("Microsoft YaHei", 9), wraplength=250, justify="left",
                anchor="w").pack(anchor="w", fill="x", pady=1)

        # 用户标签编辑
        ut = cfg.get("user_tags", "") or ""
        tv = tk.StringVar(value=ut)
        tk.Entry(card, textvariable=tv, bg="#ffffff", fg="#1b5e20",
                font=("Microsoft YaHei", 9), relief="solid").pack(fill="x", pady=2)

        # 评分（仅在拖动释放时写入DB，避免每像素都触发写入）
        sf = tk.Frame(card, bg="#f1f8e9"); sf.pack(fill="x", pady=1)
        sv = tk.IntVar(value=cfg.get("score", 3))
        _scale = tk.Scale(sf, from_=1, to=5, variable=sv, orient="horizontal", length=90,
                bg="#f1f8e9", fg="#1b5e20", troughcolor="#c8e6c9")
        _scale.bind("<ButtonRelease-1>", lambda e, fid=cfg["id"], sv=sv: self._on_db_score(fid, sv.get()))
        _scale.pack(side="left")
        tk.Label(sf, text=f"{sv.get()} STAR", bg="#f1f8e9", fg="#ffb74d",
                font=("Microsoft YaHei", 9)).pack(side="left", padx=4)

        # 选择框 + 保存按钮
        sel_var = tk.BooleanVar(value=False)
        tk.Checkbutton(card, text="选", variable=sel_var, bg="#f1f8e9",
                      fg="#1b5e20", selectcolor="#c8e6c9",
                      font=("Microsoft YaHei", 9)).pack(anchor="w")

        RoundedButton(card, text="保存修改", height=26,
                     bg_color="#0d6efd", fg_color="#ffffff",
                     hover_color="#0b5ed7", radius=6,
                     command=lambda fid=cfg["id"], tvar=tv, svar=sv:
                         self._save_db_frame(fid, svar.get(), tvar.get())
                     ).pack(pady=(4, 0))

        fw = {
            "id": cfg["id"], "tag_text": tag_text, "tv": tv,
            "sv": sv, "sel": sel_var, "card": card, "from_db": True
        }
        self._fw.append(fw)
        self._frame_idx_map[i] = fw

    def _on_db_score(self, frame_id: int, score: int):
        try:
            from core.database import db
            db.update_frame_score(frame_id, score)
        except Exception:
            pass

    def _save_db_frame(self, frame_id: int, score: int, user_tags: str):
        try:
            from core.database import db
            db.update_frame_score(frame_id, score)
            db.update_frame_tags(frame_id, user_tags)
            # v11.6: 同步更新脚本偏好(如果当前视频有脚本哈希)
            if self._current_video:
                shash = make_script_hash(Path(self._current_video).name)
                db.update_script_preference(shash, self._current_video, score)
            self._fb_lbl.config(text=f"[OK] 帧#{frame_id} 已保存", foreground="#43a047")
            self._refresh_stats()
        except Exception as e:
            self._fb_lbl.config(text=f"保存失败: {e}", foreground="#e53935")

    # ═══════════════════════════════════════════════════════════
    # 全帧识别 — 单视频
    # ═══════════════════════════════════════════════════════════
    def _recognize_current(self):
        """识别当前选中的视频"""
        if not self._current_video or not os.path.exists(self._current_video):
            messagebox.showinfo("提示",
                "请先在左侧选择视频:\n1. 点击文件夹加载视频列表\n2. 点击一个视频文件\n3. 再点击「启动全帧识别」")
            return
        if self._analyzing:
            messagebox.showinfo("提示", "识别进行中，请等待或点击取消")
            return
        self._analyzing = True
        self._batch_running = False
        self._status_lbl.config(text="初始化...")
        self._progress["value"] = 0; self._pg_lbl.config(text="")
        self._clear_frames()

        from core.frame_annotator import FrameAnnotator

        def _pg(msg, pct):
            self.app.root.after(0, lambda: (
                self._status_lbl.config(text=msg),
                self._progress.configure(value=int(pct * 100)),
                self._pg_lbl.config(text=f"{int(pct * 100)}%")
            ))

        def _frame_ready(ann):
            self.app.root.after(0, lambda a=ann: self._add_frame_card(a))

        def _tag_ready(idx, model_tags, user_tags):
            self.app.root.after(0, lambda: self._update_frame_tags(idx, model_tags, user_tags))

        self._annotator = FrameAnnotator(
            progress_callback=_pg,
            frame_ready_callback=_frame_ready,
            tag_ready_callback=_tag_ready
        )

        def _run():
            n = self._annotator.extract_frames(self._current_video)
            if n == 0:
                self.app.root.after(0, lambda: self._status_lbl.config(text="无帧"))
                self._analyzing = False
                return
            self._annotator.init_models()
            self._annotator.run_models_streaming(max_workers=2)
            self.app.root.after(0, self._on_done)

        threading.Thread(target=_run, daemon=True).start()

    def _add_frame_card(self, ann):
        """添加单帧卡片 — 放大版 (240x180)"""
        i = ann.frame_index
        card = tk.Frame(self._frame_inner, bg="#f1f8e9", bd=1, relief="solid",
                       padx=6, pady=6)
        col = i % 3  # 每行3个卡片
        row = i // 3
        card.grid(row=row, column=col, sticky="nsew", padx=3, pady=3)

        # 帧号 + 时间戳
        tk.Label(card, text=f"#{i} {ann.timestamp_str}", bg="#f1f8e9",
                fg="#2e7d32", font=("Consolas", 10, "bold")).pack(anchor="w")

        # 缩略图 — 240x180
        if HAS_PIL and ann.frame_path and os.path.exists(ann.frame_path):
            try:
                img = Image.open(ann.frame_path)
                img.thumbnail((240, 180), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                lbl_img = tk.Label(card, image=photo, bg="#f1f8e9")
                lbl_img.image = photo
                lbl_img.pack(pady=3)
            except Exception:
                tk.Label(card, text="[无法加载图片]", bg="#f1f8e9", fg="#ccc",
                        font=("Microsoft YaHei", 9)).pack(pady=4)
        else:
            tk.Label(card, text="[图片待加载]", bg="#f1f8e9", fg="#ccc",
                    font=("Microsoft YaHei", 9)).pack(pady=4)

        # 模型标签 — 字体放大到 9, wraplength=250
        tag_text = tk.StringVar(value="[AI] 识别中...")
        tk.Label(card, textvariable=tag_text, bg="#f1f8e9", fg="#4a7c4f",
                font=("Microsoft YaHei", 9), wraplength=250, justify="left",
                anchor="w").pack(anchor="w", fill="x", pady=1)

        # 可编辑标签 — 字体 9, 宽度放大
        tv = tk.StringVar(value="")
        tk.Entry(card, textvariable=tv, bg="#ffffff", fg="#1b5e20",
                font=("Microsoft YaHei", 9), relief="solid").pack(fill="x", pady=2)

        # 评分
        sf = tk.Frame(card, bg="#f1f8e9"); sf.pack(fill="x", pady=1)
        sv = tk.IntVar(value=ann.score)
        tk.Scale(sf, from_=1, to=5, variable=sv, orient="horizontal", length=90,
                bg="#f1f8e9", fg="#1b5e20", troughcolor="#c8e6c9",
                command=lambda v, a=ann: setattr(a, 'score', int(v))).pack(side="left")
        tk.Label(sf, text=f"{ann.score} STAR", bg="#f1f8e9", fg="#ffb74d",
                font=("Microsoft YaHei", 9)).pack(side="left", padx=4)

        sel_var = tk.BooleanVar(value=False)
        tk.Checkbutton(card, text="选", variable=sel_var, bg="#f1f8e9",
                      fg="#1b5e20", selectcolor="#c8e6c9",
                      font=("Microsoft YaHei", 9),
                      command=lambda sv=sel_var, a=ann: setattr(a, 'selected', sv.get())
                      ).pack(anchor="w")

        fw = {"tag_text": tag_text, "tv": tv, "sv": sv, "sel": sel_var,
              "ann": ann, "card": card, "from_db": False}
        self._fw.append(fw)
        self._frame_idx_map[i] = fw

    def _update_frame_tags(self, idx, model_tags, user_tags):
        if idx not in self._frame_idx_map:
            return
        fw = self._frame_idx_map[idx]
        parts = []
        for model, tags in list(model_tags.items())[:3]:
            t = ", ".join(tags[:4]) if tags else "(none)"
            parts.append(f"{model}: {t}")
        fw["tag_text"].set("\n".join(parts) if parts else "[AI] (none)")
        fw["tv"].set(", ".join(user_tags[:8]))


    def reload_current_video(self):
        """v11.4: 从数据库重新加载当前视频的帧数据"""
        if not self._current_video:
            return
        self._status_lbl.config(text=f"刷新中: {Path(self._current_video).name[:40]}")
        def _r():
            self._load_frames_from_db(self._current_video)
        threading.Thread(target=_r, daemon=True).start()

    def _on_db_data_changed(self, video_path):
        """v11.4: 数据库变更回调 — 如果是当前视频则重新加载"""
        if video_path == self._current_video:
            self.app.root.after(0, lambda: self.reload_current_video())
    def _on_done(self):
        self._analyzing = False
        if self._annotator:
            self._annotator.cleanup()
        if not self._annotator or not self._annotator.frames:
            self._status_lbl.config(text="无帧")
            return
        frames = self._annotator.frames
        models = self._annotator._models
        self._status_lbl.config(text=f"完成: {len(frames)}帧 | 模型: {models}")
        self._progress["value"] = 100; self._pg_lbl.config(text="100%")

    def _on_cancel(self):
        if self._annotator:
            self._annotator.cancel()
            self._annotator.cleanup()
        self._analyzing = False
        self._batch_running = False
        self._batch_cancel.set()
        self._status_lbl.config(text="已取消")

    def _on_preview(self):
        if self._current_video and os.path.exists(self._current_video):
            os.startfile(self._current_video)

    # ═══════════════════════════════════════════════════════════
    # 自动批量识别（所有视频）
    # ═══════════════════════════════════════════════════════════
    def _batch_recognize_all(self):
        """批量识别左侧视频列表中的所有视频"""
        if not self._video_paths:
            messagebox.showinfo("提示", "请先加载视频列表（点击文件夹或驱动器）")
            return
        if self._analyzing or self._batch_running:
            messagebox.showinfo("提示", "识别正在进行中")
            return

        total = len(self._video_paths)
        ok = messagebox.askyesno("确认批量识别",
            f"将对 {total} 个视频执行全帧识别。\n\n"
            f"此操作耗时较长（每个视频约 1-5 分钟），\n"
            f"可以在过程中随时停止。\n\n是否继续？")
        if not ok:
            return

        self._batch_running = True
        self._batch_cancel.clear()
        self._batch_stop_btn.configure(state="normal")
        self._status_lbl.config(text=f"批量识别开始: 0/{total}")
        self._progress["value"] = 0
        self._progress.configure(maximum=total)
        self._pg_lbl.config(text=f"0/{total}")

        # 收集结果
        self._batch_queue = queue.Queue()

        def _run_batch():
            import concurrent.futures as _cfut
            import gc as _gc
            success = 0
            fail = 0
            last_vp = None
            for idx, vp in enumerate(self._video_paths):
                if self._batch_cancel.is_set():
                    self._batch_queue.put(("log", "批显停止 (%d/%d)" % (success, idx)))
                    break

                vname = Path(vp).name
                self._batch_queue.put(("status", "[%d/%d] %s" % (idx+1, total, vname[:50])))
                self._batch_queue.put(("progress", idx))
                self._append_batch_log("[%d/%d] %s" % (idx+1, total, vname))

                video_ok = False
                video_error = ""
                with _cfut.ThreadPoolExecutor(max_workers=1) as inner:
                    fut = inner.submit(self._recognize_single_video_sync, vp, self._batch_cancel)
                    try:
                        fut.result(timeout=600)
                        video_ok = True
                    except _cfut.TimeoutError:
                        video_error = "超时(10min)"
                        self._batch_cancel.set()
                    except Exception as e:
                        video_error = str(e)[:100]

                if self._batch_cancel.is_set() and not video_ok:
                    self._batch_cancel.clear()

                if video_ok:
                    success += 1
                    last_vp = vp
                    self._batch_queue.put(("log", "  OK %s" % vname))
                    self._append_batch_log("  OK %s" % vname)
                    _gc.collect()
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    except Exception:
                        pass
                else:
                    fail += 1
                    self._batch_queue.put(("log", "  FAIL %s: %s" % (vname, video_error)))
                    self._append_batch_log("  FAIL %s: %s" % (vname, video_error))

            self._batch_queue.put(("progress", total))
            self._batch_queue.put(("status", "批显完成: %d/%d" % (success, len(self._video_paths))))
            self._batch_queue.put(("done", None))
            self._append_batch_log("=== 完成: %d成功/%d失败/%d总 ===" % (success, fail, total))

            self.app.root.after(300, self._refresh_stats)
            if last_vp:
                self.app.root.after(500, lambda v=last_vp: self._load_frames_from_db(v))

        threading.Thread(target=_run_batch, daemon=True).start()
        self._poll_batch_queue()

    def _recognize_single_video_sync(self, video_path: str, cancel_event):
        """同步识别单个视频（在批量线程中调用）"""
        from core.frame_annotator import FrameAnnotator
        import tempfile, shutil, time as _time

        annotator = FrameAnnotator()
        try:
            n = annotator.extract_frames(video_path)
            if n == 0:
                annotator.cleanup()
                return

            annotator.init_models()

            # 串行识别每帧
            for i, ann in enumerate(annotator.frames):
                if cancel_event.is_set():
                    annotator.cleanup()
                    return
            annotator.run_models()
        except Exception as e:
            annotator.cleanup()
            raise

        # 保存到 video_frames 表
        vname = Path(video_path).name
        try:
            from core.database import db
            import hashlib
            video_hash = hashlib.md5(video_path.encode()).hexdigest()[:12]
            frames_dir = str(Path(__file__).parent.parent / "shipin" / "frames" / video_hash)
            os.makedirs(frames_dir, exist_ok=True)

            for ann in annotator.frames:
                # 复制帧图片到永久目录
                safe_ts = f"{ann.timestamp_sec:.3f}".replace(".", "_")
                perm_path = os.path.join(frames_dir, f"frame_{safe_ts}s.jpg")
                try:
                    shutil.copy2(ann.frame_path, perm_path)
                except Exception:
                    perm_path = ann.frame_path

                # 收集标签
                all_tags = set()
                for tags in ann.model_tags.values():
                    all_tags.update(tags)

                frame_data = {
                    "video_path": video_path,
                    "frame_timestamp": ann.timestamp_sec,
                    "frame_image_path": perm_path,
                    "caption": "",
                    "objects": ", ".join(all_tags)[:500] if all_tags else "",
                    "materials": "",
                    "colors": "",
                    "style": "",
                    "scene_type": "标注帧",
                    "model_confidence": 0.8,
                }
                try:
                    db.insert_frame(frame_data)
                except Exception:
                    pass

            # 标记 has_frames
            try:
                with db.get_connection() as conn:
                    conn.execute(
                        "UPDATE materials SET has_frames = 1 WHERE video_path = ?",
                        (video_path,))
            except Exception:
                pass

        except Exception:
            pass

        annotator.cleanup()

    def _append_batch_log(self, msg: str):
        """向批量识别日志框追加一行"""
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.tab.after(0, lambda: (
            self._batch_log.configure(state="normal"),
            self._batch_log.insert("end", f"[{ts}] {msg}\n"),
            self._batch_log.see("end"),
            self._batch_log.configure(state="disabled"),
        ))

    def _poll_batch_queue(self):
        """轮询批量识别队列，更新UI"""
        try:
            while True:
                msg_type, payload = self._batch_queue.get_nowait()
                if msg_type == "status":
                    self._status_lbl.config(text=payload)
                elif msg_type == "progress":
                    self._progress["value"] = payload
                    total = len(self._video_paths)
                    self._pg_lbl.config(text=f"{payload}/{total}")
                elif msg_type == "log":
                    # 日志累积到状态栏
                    self._fb_lbl.config(text=payload, foreground="#4a7c4f")
                elif msg_type == "done":
                    self._batch_running = False
                    self._batch_stop_btn.configure(state="disabled")
                    self._status_lbl.config(
                        text="批量识别完成 — 点击视频查看帧结果")
                    self._progress["value"] = self._progress.get("maximum", 100)
                    messagebox.showinfo("完成", self._status_lbl.cget("text"))
        except queue.Empty:
            pass

        if self._batch_running:
            self.tab.after(200, self._poll_batch_queue)

    def _stop_batch(self):
        if self._batch_running:
            self._batch_cancel.set()
            self._batch_stop_btn.configure(state="disabled")
            self._status_lbl.config(text="正在停止批量识别...")

    # ═══════════════════════════════════════════════════════════
    # 批量操作 + 反馈
    # ═══════════════════════════════════════════════════════════
    def _sel_all(self, on):
        for fw in self._fw:
            fw["sel"].set(on)
            if fw.get("ann"):
                fw["ann"].selected = on
        self._sel_lbl.config(text=f"已选:{sum(1 for f in self._fw if f['sel'].get())}")

    def _batch_edit(self):
        sel = [f for f in self._fw if f["sel"].get()]
        if not sel:
            messagebox.showinfo("提示", "请先勾选关键帧")
            return
        top = tk.Toplevel(self.app.root)
        top.title("批量修改标签")
        top.geometry("420x130")
        tk.Label(top, text="输入标签(逗号分隔):", font=("Microsoft YaHei", 10)).pack(pady=8)
        e = tk.Entry(top, width=45, font=("Microsoft YaHei", 10)); e.pack(pady=4); e.focus()
        def _apply():
            tags = [t.strip() for t in e.get().split(",") if t.strip()]
            for f in sel:
                f["tv"].set(", ".join(tags))
                if f.get("from_db") and f.get("id"):
                    self._save_db_frame(f["id"], f["sv"].get(), ", ".join(tags))
                elif f.get("ann"):
                    f["ann"].user_tags = tags
                    f["ann"].edited = True
            top.destroy()
        tk.Button(top, text="应用", command=_apply, font=("Microsoft YaHei", 10)).pack(pady=8)

    def _on_feedback(self):
        if self._annotator and self._annotator.frames:
            for fw in self._fw:
                if not fw.get("from_db") and fw.get("ann"):
                    tags = [t.strip() for t in fw["tv"].get().split(",") if t.strip()]
                    if tags != fw["ann"].user_tags:
                        fw["ann"].user_tags = tags
                        fw["ann"].edited = True
            n = self._annotator.save_feedback()
            self._fb_lbl.config(text=f"[OK] {n}条修正已学习", foreground="#43a047")
        elif self._fw and self._fw[0].get("from_db"):
            # 处理已加载的DB帧
            count = 0
            for fw in self._fw:
                if fw.get("id") and fw.get("from_db"):
                    self._save_db_frame(fw["id"], fw["sv"].get(), fw["tv"].get())
                    count += 1
            self._fb_lbl.config(text=f"[OK] {count}条已保存", foreground="#43a047")
        else:
            messagebox.showinfo("提示", "没有可提交的帧数据")
        self._refresh_stats()

    def _refresh_stats(self):
        try:
            from core.database import db
            with db.get_connection() as conn:
                total = conn.execute("SELECT COUNT(*) FROM video_frames").fetchone()[0]
                scored = conn.execute(
                    "SELECT COUNT(*) FROM video_frames WHERE user_score != 3").fetchone()[0]
                videos = conn.execute(
                    "SELECT COUNT(DISTINCT video_path) FROM video_frames").fetchone()[0]
            self._stats_lbl.config(
                text=f"帧DB: {total}帧 | 已评分: {scored} | 视频: {videos}")
        except Exception:
            self._stats_lbl.config(text="统计加载中...")

    @staticmethod
    def _fmt_ts(sec):
        m, s = divmod(int(sec), 60)
        h, m = divmod(m, 60)
        ms = int((sec % 1) * 100)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:02d}"
