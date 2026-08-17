"""
树剪 — 素材库管理 Tab
批量分析、进度显示、手动编辑标签、FAISS索引管理
"""
import os, threading, time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext


class LibraryTab:
    """素材库管理面板 — 嵌入到主窗口的 Notebook"""

    def __init__(self, notebook, app):
        self.app = app
        self.tab = ttk.Frame(notebook)
        notebook.add(self.tab, text="AI素材库 / AI Library")
        self._build()
        self._analyzer = None
        self._builder = None
        self._analyzing = False

    def _build(self):
        frm = ttk.Frame(self.tab, padding=10)
        frm.pack(fill="both", expand=True)

        # ── 控制栏 ──
        bf = ttk.Frame(frm); bf.pack(fill="x", pady=4)
        ttk.Button(bf, text="🔍 扫描待分析视频 / Scan Pending",
                  command=self._on_scan_pending).pack(side="left", padx=4)
        ttk.Button(bf, text="▶ 开始批量分析 / Start Batch Analysis",
                  command=self._on_start_analysis).pack(side="left", padx=4)
        ttk.Button(bf, text="⏹ 停止 / Stop",
                  command=self._on_stop_analysis).pack(side="left", padx=4)
        ttk.Button(bf, text="📊 重建FAISS索引 / Rebuild Index",
                  command=self._on_rebuild_index).pack(side="left", padx=4)
        self.lib_status = ttk.Label(bf, text="就绪 / Ready",
                                   foreground="#8892b0")
        self.lib_status.pack(side="left", padx=12)

        # ── 进度条 ──
        pf = ttk.Frame(frm); pf.pack(fill="x", pady=4)
        self.lib_progress = ttk.Progressbar(pf, mode="determinate")
        self.lib_progress.pack(fill="x", expand=True, side="left")
        self.lib_progress_label = ttk.Label(pf, text="0%", width=6)
        self.lib_progress_label.pack(side="right")

        # ── 统计面板 ──
        sf = ttk.Frame(frm); sf.pack(fill="x", pady=4)
        self.stats_labels = {}
        for i, (key, label) in enumerate([
            ("total", "总片段"), ("analyzed", "已分析"), ("pending", "待分析"), ("logs", "分析记录")
        ]):
            ttk.Label(sf, text=f"{label}:").grid(row=0, column=i*2, padx=(10,2), sticky="e")
            lbl = ttk.Label(sf, text="-", font=("Microsoft YaHei", 12, "bold"))
            lbl.grid(row=0, column=i*2+1, padx=(2,10), sticky="w")
            self.stats_labels[key] = lbl

        # ── 日志区域 ──
        self.log_area = scrolledtext.ScrolledText(frm, width=80, state="disabled",
                                                   bg="#1a1a2e", fg="#e8eaf6",
                                                   font=("Consolas", 10))
        self.log_area.pack(fill="both", expand=True, pady=4)

        self._refresh_stats()

    # ── 操作 ──

    def _on_scan_pending(self):
        """扫描待分析的视频"""
        self._log("🔍 正在扫描待分析视频...")
        self._bg_run(self._do_scan_pending, callback=self._on_scan_done)

    def _do_scan_pending(self):
        """后台扫描"""
        try:
            from core.library_builder import LibraryBuilder
            builder = LibraryBuilder()
            # 从material_engine_v3获取已注册视频
            import sqlite3
            v3db = str(Path(__file__).parent.parent / "material_engine_v3" / "database" / "material_v3.db")
            if os.path.exists(v3db):
                conn = sqlite3.connect(v3db)
                rows = conn.execute("SELECT DISTINCT path FROM videos WHERE status='scene_done' ORDER BY id LIMIT 100").fetchall()
                conn.close()
                video_paths = [r[0] for r in rows if os.path.exists(r[0])]
                pending = builder.get_pending_videos(video_paths)
                return {"total": len(video_paths), "pending": pending[:50]}  # 最多50
            return {"total": 0, "pending": []}
        except Exception as e:
            return {"error": str(e)}

    def _on_scan_done(self, result):
        if "error" in result:
            self._log(f"❌ 扫描失败: {result['error']}")
            return
        self._log(f"📊 已注册: {result['total']} 个视频")
        self._log(f"📋 待分析: {len(result['pending'])} 个")
        self._pending_videos = result.get("pending", [])

    def _on_start_analysis(self):
        """开始批量分析"""
        if not hasattr(self, '_pending_videos') or not self._pending_videos:
            messagebox.showinfo("提示", "请先点击「扫描待分析视频」")
            return

        if self._analyzing:
            messagebox.showinfo("提示", "分析任务正在进行中")
            return

        self._analyzing = True
        self._log(f"▶ 开始批量分析 {len(self._pending_videos)} 个视频...")
        self._log("🔧 正在自动检查并启动所有模型 (Ollama/CLIP/Whisper/YOLO)...")
        self.lib_progress["maximum"] = len(self._pending_videos) + 1
        self.lib_progress["value"] = 0

        def _progress(status, fname, pct):
            self.app.root.after(0, lambda: (
                self.lib_status.config(text=f"{status} | {fname[:40]}"),
                self.lib_progress_label.config(text=f"{int(pct*100)}%")
            ))

        self._bg_run(lambda: self._do_analysis(_progress), callback=self._on_analysis_done)

    def _do_analysis(self, progress_callback):
        from core.analyzer import VideoAnalyzer
        from core.library_builder import LibraryBuilder

        builder = LibraryBuilder()
        analyzer = VideoAnalyzer(progress_callback=progress_callback)

        self.app.root.after(0, lambda: self._log("   🤖 模型将在首次使用时自动加载启动 (Ollama/CLIP/Whisper/YOLO)"))
        results = []
        models_used = []

        if analyzer.vision.available:
            models_used.append("VisionModel")
        if analyzer.whisper.available:
            models_used.append("whisper")

        for i, vp in enumerate(self._pending_videos):
            if not self._analyzing:
                results.append("stopped")
                break

            self.app.root.after(0, lambda n=i: self.lib_progress.configure(value=n+1))
            try:
                source = str(Path(vp).parent.name)
                data = analyzer.analyze(vp, source_folder=source)
                if data:
                    builder.insert_analysis(data, models_used=models_used)
                    results.append("ok")
                    self.app.root.after(0, lambda: self._log(f"  ✅ {Path(vp).name[:50]}"))
                else:
                    results.append("no_frames")
            except Exception as e:
                results.append("error")
                self.app.root.after(0, lambda e=e: self._log(f"  ❌ {e}"))

        return results

    def _on_analysis_done(self, results):
        self._analyzing = False
        ok = results.count("ok") if isinstance(results, list) else 0
        self._log(f"\n✅ 分析完成: {ok}/{len(self._pending_videos)} 个")
        self._refresh_stats()
        self.lib_status.config(text="分析完成 / Analysis Done")
        self.lib_progress_label.config(text="100%")
        messagebox.showinfo("分析完成", f"成功分析 {ok} 个视频\n结果已写入数据库")

    def _on_stop_analysis(self):
        self._analyzing = False
        self.lib_status.config(text="已停止 / Stopped")
        self._log("⏹ 已请求停止")

    def _on_rebuild_index(self):
        self._log("📊 正在重建FAISS索引...")
        self._bg_run(self._do_rebuild, callback=lambda r: (
            self._log(f"✅ FAISS索引已重建"),
            self.lib_status.config(text="索引已更新 / Index Updated")
        ))

    def _do_rebuild(self):
        from core.library_builder import LibraryBuilder
        builder = LibraryBuilder()
        builder.build_faiss_index()

    # ── 辅助 ──

    def _refresh_stats(self):
        try:
            from core.library_builder import LibraryBuilder
            builder = LibraryBuilder()
            stats = builder.get_stats()
            total_vids = stats.get("total_videos", 0)
            analyzed = stats.get("analyzed_videos", 0)
            self.stats_labels["total"].config(text=str(stats.get("total_segments", 0)))
            self.stats_labels["analyzed"].config(text=str(analyzed))
            self.stats_labels["pending"].config(text=str(total_vids - analyzed))
            self.stats_labels["logs"].config(text=str(stats.get("analysis_logs", 0)))
        except Exception as e:
            self._log(f"统计刷新失败: {e}")

    def _log(self, msg):
        self.log_area.config(state="normal")
        self.log_area.insert("end", msg + "\n")
        self.log_area.see("end")
        self.log_area.config(state="disabled")

    def _bg_run(self, fn, callback=None):
        def _r():
            try:
                result = fn()
            except Exception as e:
                result = {"error": str(e)}
            if callback:
                self.app.root.after(0, lambda r=result: callback(r))
        threading.Thread(target=_r, daemon=True).start()
