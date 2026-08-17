"""
树剪 TreeCut v11.3 — 全新素材库标签页
======================================
以视频为单位展示所有分析帧，每帧显示缩略图/标签/打分/编辑。
支持滚轮滚动、实时同步后台扫描结果。

帧级可视化浏览器 — 替代旧版简单Treeview。
"""

import os
import sys
import json
import time
import threading
import queue
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import tkinter as tk
from tkinter import messagebox, scrolledtext
import ttkbootstrap as tb

from ui.rounded_button import RoundedButton

# PIL 可选 — 用于缩略图加载
try:
    from PIL import Image, ImageTk
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


# ═══════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════

def _format_time(seconds: float) -> str:
    """秒 → mm:ss.fff"""
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m:02d}:{s:06.3f}"


def _truncate(text: str, max_len: int = 60) -> str:
    if not text:
        return ""
    text = str(text)
    return text[:max_len] + ("..." if len(text) > max_len else "")


def _count_frames_for_video(video_path: str, db) -> int:
    """快速获取某个视频的总帧数"""
    try:
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM video_frames WHERE video_path = ?",
                (video_path,)
            ).fetchone()
            return row[0] if row else 0
    except Exception:
        return 0


# ═══════════════════════════════════════════════════
# 星星打分组件
# ═══════════════════════════════════════════════════

class StarRating(tb.Frame):
    """5颗星打分控件"""

    def __init__(self, parent, rating: int = 3, on_change=None):
        super().__init__(parent)
        self.rating = tk.IntVar(value=rating)
        self.on_change = on_change
        self._star_labels = []
        self._build()

    def _build(self):
        for i in range(1, 6):
            lbl = tb.Label(self, text="★", font=("", 14),
                          foreground="#ffc107" if i <= self.rating.get() else "#ccc",
                          cursor="hand2", padding=(1, 0))
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e, v=i: self._set_rating(v))
            lbl.bind("<Enter>", lambda e, idx=i: self._hover(idx))
            lbl.bind("<Leave>", lambda e: self._refresh_display())
            self._star_labels.append(lbl)

    def _set_rating(self, val: int):
        self.rating.set(val)
        self._refresh_display()
        if self.on_change:
            self.on_change(val)

    def _hover(self, val: int):
        for i, lbl in enumerate(self._star_labels, 1):
            lbl.config(foreground="#ffc107" if i <= val else "#ccc")

    def _refresh_display(self):
        r = self.rating.get()
        for i, lbl in enumerate(self._star_labels, 1):
            lbl.config(foreground="#ffc107" if i <= r else "#ccc")

    def set(self, val: int):
        self.rating.set(val)
        self._refresh_display()


# ═══════════════════════════════════════════════════
# 帧放大查看窗口
# ═══════════════════════════════════════════════════

class FrameZoomWindow:
    """弹出一个独立窗口，显示原始尺寸帧图片和完整标签，支持编辑"""

    def __init__(self, parent, frame_data: dict, db, on_save=None):
        self.parent = parent
        self.frame_data = frame_data
        self.db = db
        self.on_save = on_save
        self._window = tk.Toplevel(parent)
        self._window.title(f"帧详情 — {_format_time(frame_data.get('frame_timestamp', 0))}")
        self._window.geometry("820x700")
        self._window.configure(bg="#e8f5e9")
        self._build()

    def _build(self):
        fd = self.frame_data

        # ── 图片 ──
        img_path = fd.get("frame_image_path", "")
        if img_path and os.path.exists(img_path) and _HAS_PIL:
            try:
                img = Image.open(img_path)
                img.thumbnail((600, 400), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                img_lbl = tb.Label(self._window, image=photo, background="#e8f5e9")
                img_lbl.image = photo
                img_lbl.pack(pady=6)
            except Exception:
                tb.Label(self._window, text="(图片加载失败)",
                        background="#e8f5e9").pack(pady=10)
        else:
            tb.Label(self._window, text=f"图片: {img_path or '(无)'}",
                    background="#e8f5e9").pack(pady=10)

        # ── 信息 ──
        info_frame = tb.Labelframe(self._window, text="帧信息", padding=6)
        info_frame.pack(fill="x", padx=10, pady=4)

        info_text = (
            f"视频: {_truncate(fd.get('video_path',''), 80)}\n"
            f"时间戳: {_format_time(fd.get('frame_timestamp',0))}\n"
            f"场景类型: {fd.get('scene_type','')}\n"
            f"置信度: {fd.get('model_confidence','')}\n"
            f"描述: {fd.get('caption','')}\n"
        )
        tb.Label(info_frame, text=info_text, font=("Microsoft YaHei", 10),
                justify="left", background="#e8f5e9").pack(anchor="w")

        # ── 标签编辑 ──
        tag_frame = tb.Labelframe(self._window, text="编辑标签 (逗号分隔)", padding=6)
        tag_frame.pack(fill="x", padx=10, pady=4)

        current_tags = fd.get("user_tags", "") or ""
        current_raw = ", ".join([
            fd.get("objects", ""), fd.get("materials", ""),
            fd.get("colors", ""), fd.get("style", ""),
        ])
        if not current_tags.strip():
            current_tags = current_raw

        self._tag_var = tk.StringVar(value=current_tags)
        tag_entry = tb.Entry(tag_frame, textvariable=self._tag_var, font=("Microsoft YaHei", 10))
        tag_entry.pack(fill="x", pady=2)

        # ── 打分 ──
        score_frame = tb.Frame(self._window)
        score_frame.pack(fill="x", padx=10, pady=4)
        tb.Label(score_frame, text="评分:", font=("Microsoft YaHei", 11, "bold"),
                background="#e8f5e9").pack(side="left", padx=4)
        self._star = StarRating(score_frame, rating=fd.get("user_score", 3))
        self._star.pack(side="left", padx=6)

        # ── 按钮 ──
        btn_frame = tb.Frame(self._window, padding=6)
        btn_frame.pack(fill="x", padx=10)

        def _save():
            new_tags = self._tag_var.get().strip()
            new_score = self._star.rating.get()
            frame_id = fd.get("id")
            if frame_id:
                try:
                    self.db.update_frame_tags(frame_id, new_tags)
                    self.db.update_frame_score(frame_id, new_score)
                    if self.on_save:
                        self.on_save(frame_id, new_score, new_tags)
                except Exception as e:
                    messagebox.showerror("错误", f"保存失败: {e}")
            self._window.destroy()

        RoundedButton(btn_frame, text="💾 保存并关闭", command=_save,
                     width=140, height=36, bg_color="#0d6efd",
                     fg_color="#ffffff", hover_color="#0b5ed7", radius=10
                     ).pack(side="left", padx=4)
        RoundedButton(btn_frame, text="关闭", command=self._window.destroy,
                     width=90, height=36, bg_color="#e0e0e0",
                     fg_color="#212529", hover_color="#d0e0ff", radius=10
                     ).pack(side="left", padx=4)


# ═══════════════════════════════════════════════════
# 帧卡片 (在网格中显示)
# ═══════════════════════════════════════════════════

class FrameCard(tb.Frame):
    """网格视图中的单个帧卡片"""

    def __init__(self, parent, frame_data: dict, db, on_update=None):
        super().__init__(parent, relief="groove", borderwidth=1, padding=3)
        self.frame_data = frame_data
        self.db = db
        self.on_update = on_update
        self._thumbnail_image = None
        self._build()

    def _build(self):
        fd = self.frame_data
        w = 200

        # ── 缩略图 ──
        img_path = fd.get("frame_image_path", "")
        if img_path and os.path.exists(img_path) and _HAS_PIL:
            try:
                img = Image.open(img_path)
                img.thumbnail((w, int(w * 0.75)), Image.LANCZOS)
                self._thumbnail_image = ImageTk.PhotoImage(img)
                img_lbl = tb.Label(self, image=self._thumbnail_image)
                img_lbl.pack()
                img_lbl.bind("<Double-1>", lambda e: self._zoom())
            except Exception:
                placeholder = tk.Canvas(self, width=w, height=int(w * 0.75), bg="#ddd")
                placeholder.create_text(w//2, int(w*0.75)//2,
                                       text="图片加载失败", fill="#999")
                placeholder.pack()
        else:
            placeholder = tk.Canvas(self, width=w, height=int(w * 0.75), bg="#eee")
            placeholder.create_text(w//2, int(w*0.75)//2,
                                   text="无图片", fill="#999")
            placeholder.pack()

        # ── 时间戳 ──
        ts = _format_time(fd.get("frame_timestamp", 0))
        tb.Label(self, text=ts, font=("Consolas", 10, "bold"),
                foreground="#1b5e20").pack(pady=1)

        # ── 场景 ──
        scene = fd.get("scene_type", "") or fd.get("style", "") or ""
        if scene:
            tb.Label(self, text=scene[:20], font=("Microsoft YaHei", 8),
                    foreground="#666").pack()

        # ── 标签摘要 ──
        tags_text = fd.get("user_tags", "") or fd.get("objects", "") or ""
        if tags_text:
            tb.Label(self, text=_truncate(tags_text, 25),
                    font=("Microsoft YaHei", 8), foreground="#888",
                    wraplength=w-10).pack(pady=1)

        # ── 打分 ──
        star = StarRating(self, rating=fd.get("user_score", 3),
                         on_change=lambda v, fid=fd.get("id"): self._on_score_change(fid, v))
        star.pack(pady=2)

        # ── 按钮行 ──
        btn_row = tb.Frame(self)
        btn_row.pack(pady=(2, 0))

        edit_btn = tb.Button(btn_row, text="编辑", width=6,
                           command=self._zoom, bootstyle="outline-secondary")
        edit_btn.pack(side="left", padx=1)

        # 双击放大
        self.bind("<Double-1>", lambda e: self._zoom())
        for child in self.winfo_children():
            try:
                child.bind("<Double-1>", lambda e: self._zoom())
            except Exception:
                pass

    def _on_score_change(self, frame_id, score):
        """快速打分"""
        try:
            self.db.update_frame_score(frame_id, score)
            if self.on_update:
                self.on_update(frame_id, score, None)
        except Exception:
            pass

    def _zoom(self):
        """打开放大查看窗口"""
        FrameZoomWindow(self.winfo_toplevel(), self.frame_data, self.db,
                       on_save=self.on_update)

    def refresh_data(self, new_data: dict):
        """更新帧数据"""
        self.frame_data = new_data


# ═══════════════════════════════════════════════════
# 视频卡片 (可展开显示帧网格)
# ═══════════════════════════════════════════════════

class VideoCard(tb.Labelframe):
    """单个视频的卡片 — 点击展开显示帧网格"""

    def __init__(self, parent, video_path: str, frame_summary: dict, db,
                 on_feedback=None, library_tab=None):
        text = f"📹 {_truncate(Path(video_path).name, 50)}"
        super().__init__(parent, text=text, padding=6)
        self.video_path = video_path
        self.frame_summary = frame_summary
        self.db = db
        self.on_feedback = on_feedback
        self.library_tab = library_tab
        self._expanded = False
        self._frames_loaded = False
        self._frame_cards = []
        self._frame_grid_frame = None
        self._build()

    def _build(self):
        fs = self.frame_summary

        # ── 摘要行 ──
        summary_frame = tb.Frame(self)
        summary_frame.pack(fill="x")

        info_text = (
            f"帧数: {fs.get('frame_count',0)} | "
            f"均分: {fs.get('avg_score','-')} | "
            f"最后分析: {(fs.get('last_analyzed','') or '')[:16]} | "
            f"素材: {_truncate(fs.get('all_materials','') or fs.get('all_objects',''), 40)}"
        )
        tb.Label(summary_frame, text=info_text, font=("Microsoft YaHei", 9),
                foreground="#4a7c4f").pack(side="left", fill="x", expand=True)

        # 展开/折叠按钮
        self._toggle_btn = RoundedButton(
            summary_frame, text="▶ 展开帧 / Expand",
            command=self._toggle_expand, width=150, height=30,
            bg_color="#e0e0e0", fg_color="#212529",
            hover_color="#d0e0ff", radius=8
        )
        self._toggle_btn.pack(side="right", padx=4)

    def _toggle_expand(self):
        if self._expanded:
            self._collapse()
        else:
            self._expand()

    def _expand(self):
        self._expanded = True
        self._toggle_btn.configure(text="▼ 折叠 / Collapse")

        # 加载帧数据
        if not self._frames_loaded:
            self._frames_loaded = True
            self._frame_grid_frame = tb.Frame(self)
            self._frame_grid_frame.pack(fill="x", pady=6)

            # 后台线程加载帧
            threading.Thread(target=self._load_frames, daemon=True).start()
        else:
            if self._frame_grid_frame:
                self._frame_grid_frame.pack(fill="x", pady=6)

    def _collapse(self):
        self._expanded = False
        self._toggle_btn.configure(text="▶ 展开帧 / Expand")
        if self._frame_grid_frame:
            self._frame_grid_frame.pack_forget()

    def _load_frames(self):
        """后台加载帧数据 → UI线程创建FrameCard"""
        try:
            frames = self.db.get_frames_by_video(self.video_path)
        except Exception:
            frames = []

        def _build_cards():
            if not self._frame_grid_frame:
                return

            for w in self._frame_grid_frame.winfo_children():
                w.destroy()
            self._frame_cards = []

            if not frames:
                tb.Label(self._frame_grid_frame, text="(无帧数据, 请先运行全盘扫描)",
                        font=("Microsoft YaHei", 10),
                        foreground="#999").pack(pady=10)
                return

            # 流式网格布局 — 每行4个
            row_frame = None
            col = 0
            for i, fd in enumerate(frames):
                if col == 0:
                    row_frame = tb.Frame(self._frame_grid_frame)
                    row_frame.pack(fill="x", pady=3)
                col = (i % 4) + 1
                card = FrameCard(row_frame, fd, self.db, on_update=self._on_frame_update)
                card.pack(side="left", padx=4, pady=2)
                self._frame_cards.append(card)
                if col == 4:
                    col = 0

            # 更新摘要
            self._update_summary(frames)

        self.winfo_toplevel().after(0, _build_cards)

    def _on_frame_update(self, frame_id, score, tags):
        """帧评分/标签更新回调"""
        # 更新摘要数据
        if self.on_feedback:
            self.on_feedback(frame_id, score, tags)

    def _update_summary(self, frames: list):
        """根据最新帧数据更新摘要行"""
        if frames:
            avg = sum(f.get("user_score", 3) for f in frames) / len(frames)
            self.frame_summary["avg_score"] = round(avg, 1)
            self.frame_summary["frame_count"] = len(frames)

    def add_single_frame(self, frame_data: dict):
        """实时追加单个新帧（扫描器回调）"""
        if not self._frame_grid_frame:
            return

        def _add():
            card = FrameCard(
                self._frame_grid_frame, frame_data, self.db,
                on_update=self._on_frame_update
            )
            # 简单追加到末尾
            card.pack(side="left", padx=4, pady=2)
            self._frame_cards.append(card)
            self.frame_summary["frame_count"] = (
                self.frame_summary.get("frame_count", 0) + 1
            )

        self.winfo_toplevel().after(0, _add)


# ═══════════════════════════════════════════════════
# 主素材库标签页
# ═══════════════════════════════════════════════════

class LibraryTab:
    """
    全新的素材库标签页 — 帧级别可视化浏览器。

    嵌入到 desktop.py 的 Notebook 中。
    """

    def __init__(self, notebook, app):
        """
        notebook: ttk.Notebook 实例
        app: TreeCutApp 主窗口实例（用于日志/状态）
        """
        self.app = app
        self.db = None
        self._video_cards = {}          # video_path → VideoCard
        self._frame_update_queue = queue.Queue()  # 扫描器推送队列
        self._search_var = tk.StringVar()
        self._filter_var = tk.StringVar(value="all")  # all / with_frames / high_score

        # 构建标签页
        self._frame = tb.Frame(notebook, padding=6)
        notebook.add(self._frame, text="素材库 / Library")
        self._build()

        # 加载数据库
        try:
            from core.database import db
            self.db = db
        except Exception:
            pass

        # 启动日志轮询
        self._poll_frame_queue()

        # 初始加载
        self._frame.after(500, self._refresh)

    # ═══════════ UI构建 ═══════════

    def _build(self):
        # ── 顶部工具栏 ──
        toolbar = tb.Frame(self._frame, padding=4)
        toolbar.pack(fill="x", pady=(0, 6))

        RoundedButton(toolbar, text="🔄 刷新", command=self._refresh,
                     width=90, height=34, bg_color="#0d6efd",
                     fg_color="#ffffff", hover_color="#0b5ed7", radius=8
                     ).pack(side="left", padx=2)

        RoundedButton(toolbar, text="🔍 全盘扫描",
                     command=self._start_background_scan,
                     width=100, height=34, bg_color="#28a745",
                     fg_color="#ffffff", hover_color="#218838", radius=8
                     ).pack(side="left", padx=2)

        RoundedButton(toolbar, text="📊 使用统计",
                     command=self._show_stats,
                     width=100, height=34, bg_color="#e0e0e0",
                     fg_color="#212529", hover_color="#d0e0ff", radius=8
                     ).pack(side="left", padx=2)

        # 过滤下拉
        tb.Label(toolbar, text="过滤:", font=("Microsoft YaHei", 9)).pack(side="left", padx=(20, 2))
        filter_combo = tb.Combobox(toolbar, textvariable=self._filter_var,
                                  values=["all", "with_frames", "high_score"],
                                  state="readonly", width=14)
        filter_combo.pack(side="left", padx=2)
        filter_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh())

        # 搜索框
        tb.Label(toolbar, text="搜索:", font=("Microsoft YaHei", 9)).pack(side="left", padx=(10, 2))
        search_entry = tb.Entry(toolbar, textvariable=self._search_var, width=20)
        search_entry.pack(side="left", padx=2)
        search_entry.bind("<Return>", lambda e: self._refresh())
        RoundedButton(toolbar, text="搜索", command=self._refresh,
                     width=60, height=30, bg_color="#e0e0e0",
                     fg_color="#212529", hover_color="#d0e0ff", radius=6
                     ).pack(side="left", padx=2)

        # 状态标签
        self._status_var = tk.StringVar(value="就绪")
        tb.Label(toolbar, textvariable=self._status_var,
                font=("Microsoft YaHei", 9),
                foreground="#6d6d6d").pack(side="right", padx=10)

        # ── 可滚动主区域 ──
        self._canvas_frame = tb.Frame(self._frame)
        self._canvas_frame.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(self._canvas_frame, highlightthickness=0,
                                bg="#e8f5e9")
        scrollbar = tb.Scrollbar(self._canvas_frame, orient="vertical",
                                command=self._canvas.yview, bootstyle="round")
        self._canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        # 内部内容帧
        self._content_frame = tb.Frame(self._canvas)
        self._content_id = self._canvas.create_window(
            (0, 0), window=self._content_frame, anchor="nw"
        )

        self._content_frame.bind("<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: (
            self._canvas.itemconfig(self._content_id, width=e.width)
        ))

        # 滚轮滚动
        def _on_mousewheel(event):
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self._canvas.bind("<MouseWheel>", _on_mousewheel)
        self._content_frame.bind("<MouseWheel>", _on_mousewheel)

        # 底部页脚
        footer = tb.Frame(self._frame, padding=4)
        footer.pack(fill="x")
        self._footer_var = tk.StringVar(value="")
        tb.Label(footer, textvariable=self._footer_var,
                font=("Microsoft YaHei", 9),
                foreground="#999").pack(anchor="e")

    # ═══════════ 数据加载 ═══════════

    def _refresh(self):
        """重新加载所有素材数据"""
        self._status_var.set("加载中...")
        threading.Thread(target=self._load_all, daemon=True).start()

    def _load_all(self):
        """后台加载数据 → UI线程渲染 VideoCard"""
        if self.db is None:
            try:
                from core.database import db
                self.db = db
            except Exception:
                self._update_status("数据库未就绪")
                return

        try:
            search = self._search_var.get().strip().lower()
            filter_mode = self._filter_var.get()

            summaries = self.db.get_all_video_frame_summaries(limit=200)

            # 过滤
            filtered = []
            for s in summaries:
                vp = s.get("video_path", "")
                if search and search not in vp.lower():
                    continue
                if filter_mode == "with_frames" and s.get("frame_count", 0) == 0:
                    continue
                if filter_mode == "high_score" and float(s.get("avg_score", 0)) < 3.5:
                    continue
                filtered.append(s)

            # 排序: 最新分析优先
            filtered.sort(key=lambda x: x.get("last_analyzed", "") or "", reverse=True)

            self._render_video_cards(filtered)

        except Exception as e:
            self._update_status(f"加载失败: {e}")

    def _render_video_cards(self, summaries: list):
        """在UI线程渲染视频卡片"""
        def _render():
            # 清除旧内容
            for w in self._content_frame.winfo_children():
                w.destroy()
            self._video_cards.clear()

            if not summaries:
                placeholder = tb.Labelframe(
                    self._content_frame,
                    text="素材库为空",
                    padding=20
                )
                placeholder.pack(fill="x", padx=20, pady=40)
                tb.Label(placeholder,
                        text="尚未检搜到帧分析数据。\n\n"
                             "请点击「全盘扫描」按钮，\n"
                             "对视频素材进行帧级智能分析。\n\n"
                             "扫描完成后视频帧将在此处展示。",
                        font=("Microsoft YaHei", 12),
                        justify="center",
                        foreground="#666").pack(expand=True)
                self._update_status("空 — 请运行全盘扫描")
                self._footer_var.set("")
                return

            for s in summaries:
                vp = s.get("video_path", "")
                card = VideoCard(
                    self._content_frame, vp, s, self.db,
                    library_tab=self
                )
                card.pack(fill="x", padx=10, pady=2)
                self._video_cards[vp] = card

            self._update_status(f"已加载 {len(summaries)} 个视频")
            self._footer_var.set(
                f"共 {len(summaries)} 个视频 | "
                f"总帧数: {sum(s.get('frame_count',0) for s in summaries)}"
            )

        self._frame.after(0, _render)

    def _update_status(self, msg: str):
        self._frame.after(0, lambda: self._status_var.set(msg))

    # ═══════════ 后台扫描集成 ═══════════

    def _start_background_scan(self):
        """启动后台扫描窗口"""
        try:
            from ui.background_scanner_window import BackgroundScannerWindow
            scanner = BackgroundScannerWindow(
                parent=self._frame.winfo_toplevel(),
                auto_start=False
            )
            # 注入 library_tab 引用，以便扫描器推送帧数据
            scanner._library_tab = self
            self._status_var.set("扫描窗口已打开")
        except Exception as e:
            messagebox.showerror("错误", f"启动扫描失败: {e}")

    def _poll_frame_queue(self):
        """轮询帧更新队列，处理扫描器推送"""
        try:
            while True:
                data = self._frame_update_queue.get_nowait()
                self._on_new_frame(data)
        except queue.Empty:
            pass
        self._frame.after(200, self._poll_frame_queue)

    def _on_new_frame(self, frame_data: dict):
        """扫描器推入的新帧数据 → 追加到对应 VideoCard"""
        vp = frame_data.get("video_path", "")
        if vp in self._video_cards:
            self._video_cards[vp].add_single_frame(frame_data)
        else:
            # 新视频 → 创建 VideoCard
            try:
                count = _count_frames_for_video(vp, self.db)
            except Exception:
                count = 1

            summary = {
                "video_path": vp,
                "frame_count": count,
                "avg_score": 3.0,
                "last_analyzed": datetime.now().isoformat(),
                "all_objects": frame_data.get("objects", ""),
                "all_materials": frame_data.get("materials", ""),
            }
            card = VideoCard(self._content_frame, vp, summary, self.db,
                           library_tab=self)
            card.pack(fill="x", padx=10, pady=2)
            self._video_cards[vp] = card
            self._footer_var.set(
                f"{len(self._video_cards)} 个视频 | "
                f"最新: {_truncate(Path(vp).name, 30)}"
            )

    def add_frame_from_scanner(self, frame_data: dict):
        """
        由 BackgroundScannerWindow 调用（线程安全）。
        将新帧数据放入队列，等待UI线程处理。
        """
        self._frame_update_queue.put(frame_data)

    def add_video_frames_batch(self, video_path: str, frames: list):
        """
        批量添加一个视频的所有帧（扫描完成后调用）。
        """
        def _add_all():
            # 如果已存在卡，先移除
            if video_path in self._video_cards:
                old = self._video_cards[video_path]
                old.destroy()
                del self._video_cards[video_path]

            summary = {
                "video_path": video_path,
                "frame_count": len(frames),
                "avg_score": round(
                    sum(f.get("user_score", 3) for f in frames) / max(1, len(frames)), 1
                ),
                "last_analyzed": datetime.now().isoformat(),
                "all_objects": ", ".join(
                    set(f.get("objects", "") for f in frames if f.get("objects"))
                )[:100],
                "all_materials": ", ".join(
                    set(f.get("materials", "") for f in frames if f.get("materials"))
                )[:100],
            }
            card = VideoCard(self._content_frame, video_path, summary, self.db,
                           library_tab=self)
            card.pack(fill="x", padx=10, pady=2)
            self._video_cards[video_path] = card
            # 自动展开
            card._expand()
            self._update_status(f"完成: {Path(video_path).name}")
            self._footer_var.set(f"{len(self._video_cards)} 个视频")

        self._frame.after(0, _add_all)

    # ═══════════ 统计 ═══════════

    def _show_stats(self):
        """显示素材库统计弹窗"""
        if not self.db:
            return
        try:
            stats = self.db.get_stats()
            msg = (
                f"素材库统计:\n"
                f"  素材片段: {stats.get('total_segments', 0):,}\n"
                f"  已分析视频: {stats.get('analyzed_videos', 0):,}\n"
                f"  总视频注册: {stats.get('total_videos', 0):,}\n"
                f"  分析日志: {stats.get('analysis_logs', 0):,}"
            )
            messagebox.showinfo("素材库统计", msg)
        except Exception as e:
            messagebox.showerror("错误", str(e))

    # ═══════════ 清理 ═══════════

    def destroy(self):
        """清理资源"""
        self._video_cards.clear()
        self._frame.destroy()
