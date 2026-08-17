"""
树剪 TreeCut v11.2 — 后台素材扫描监控窗口
==========================================
独立的 Tkinter Toplevel 窗口，展示全盘视频扫描进度。
支持: 开始/暂停/继续/停止，实时日志，配置选项。
"""

import os
import sys
import json
import time
import queue
import threading
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext
import ttkbootstrap as tb

from ui.rounded_button import RoundedButton


class BackgroundScannerWindow:
    """
    后台全盘素材扫描监控窗口。

    用法:
        win = BackgroundScannerWindow(parent_root)
        # 窗口会自动启动扫描线程
    """

    def __init__(self, parent=None, scan_paths: list = None, auto_start: bool = True):
        self.parent = parent
        self.scan_paths = scan_paths  # None = 全盘扫描
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._paused = False
        self._running = False
        self._scanner_thread = None
        self._log_queue = queue.Queue()  # 线程安全日志队列
        self._progress_queue = queue.Queue()  # 进度队列
        self._library_tab = None  # v11.3: 素材库标签页引用，用于实时推送帧数据

        # 统计
        self._total_videos = 0
        self._scanned_count = 0
        self._island_found = 0
        self._saved_count = 0
        self._start_time = None

        # 配置
        self._frame_interval = tk.DoubleVar(value=0.25)  # 默认每秒4帧
        self._skip_analyzed = tk.BooleanVar(value=True)
        self._max_workers = tk.IntVar(value=2)

        # 构建窗口
        self._build_window()

        # 取消防线
        self._window.protocol("WM_DELETE_WINDOW", self._on_close)

        # 启动日志轮询
        self._poll_log()

        # 自动开始扫描
        if auto_start and scan_paths:
            self._window.after(500, self._start_scan)
        elif auto_start:
            # 先快速估算视频数量
            self._window.after(300, self._estimate_video_count)

    def _build_window(self):
        self._window = tk.Toplevel(self.parent) if self.parent else tb.Window(themename="litera")
        self._window.title("树剪 AI 素材库后台扫描器")
        self._window.geometry("960x720")
        self._window.configure(bg="#e8f5e9")
        self._window.minsize(700, 500)

        try:
            ico = Path(__file__).parent.parent / "tree_icon.ico"
            if ico.exists():
                self._window.iconbitmap(str(ico))
        except Exception:
            pass

        # ── 标题 ──
        title_frame = tb.Frame(self._window, padding=8)
        title_frame.pack(fill="x")
        tb.Label(title_frame, text="🌳 树剪 AI 素材库后台扫描器",
                font=("Microsoft YaHei", 16, "bold"),
                background="#e8f5e9", foreground="#1b5e20").pack(anchor="w")

        # ── 配置区 ──
        config_frame = tb.Labelframe(self._window, text="扫描配置", padding=8)
        config_frame.pack(fill="x", padx=10, pady=4)

        row1 = tb.Frame(config_frame)
        row1.pack(fill="x", pady=2)
        tb.Label(row1, text="扫描路径:", width=10).pack(side="left")
        self._path_var = tk.StringVar(value="全盘扫描 (所有磁盘)")
        self._path_entry = tb.Entry(row1, textvariable=self._path_var, state="readonly")
        self._path_entry.pack(side="left", fill="x", expand=True, padx=4)
        RoundedButton(row1, text="选择路径", command=self._choose_path,
                     width=100, height=30, bg_color="#e0e0e0",
                     fg_color="#212529", hover_color="#d0e0ff", radius=8).pack(side="left", padx=2)

        row2 = tb.Frame(config_frame)
        row2.pack(fill="x", pady=2)
        tb.Label(row2, text="抽帧间隔:", width=10).pack(side="left")
        intervals = [("每秒1帧 (1s)", 1.0), ("每秒2帧 (0.5s)", 0.5),
                     ("每秒4帧 (0.25s)", 0.25), ("每秒8帧 (0.125s)", 0.125)]
        for text, val in intervals:
            tb.Radiobutton(row2, text=text, variable=self._frame_interval,
                          value=val).pack(side="left", padx=6)

        row3 = tb.Frame(config_frame)
        row3.pack(fill="x", pady=2)
        tb.Checkbutton(row3, text="跳过已分析视频", variable=self._skip_analyzed
                      ).pack(side="left", padx=4)
        tb.Label(row3, text="并发数:").pack(side="left", padx=(20, 2))
        for v in [1, 2, 3, 4]:
            tb.Radiobutton(row3, text=str(v), variable=self._max_workers,
                          value=v).pack(side="left", padx=3)

        # ── 统计区 ──
        stat_frame = tb.Frame(self._window, padding=4)
        stat_frame.pack(fill="x", padx=10)

        self._stat_total = tk.StringVar(value="总视频: -")
        self._stat_scanned = tk.StringVar(value="已扫描: -")
        self._stat_island = tk.StringVar(value="岛台帧: -")
        self._stat_saved = tk.StringVar(value="入库: -")
        self._stat_elapsed = tk.StringVar(value="耗时: -")

        for var in [self._stat_total, self._stat_scanned, self._stat_island,
                     self._stat_saved, self._stat_elapsed]:
            tb.Label(stat_frame, textvariable=var, font=("Microsoft YaHei", 10),
                    background="#e8f5e9", foreground="#1b5e20"
                    ).pack(side="left", padx=10)

        # ── 进度条 ──
        prog_frame = tb.Frame(self._window, padding=4)
        prog_frame.pack(fill="x", padx=10)
        self._progress_bar = tb.Progressbar(prog_frame, mode="determinate", bootstyle="success")
        self._progress_bar.pack(fill="x", pady=2)
        self._current_file_var = tk.StringVar(value="就绪 - 点击「开始扫描」启动")
        tb.Label(prog_frame, textvariable=self._current_file_var,
                font=("Microsoft YaHei", 9), foreground="#6d6d6d",
                background="#e8f5e9").pack(anchor="w")

        # ── 日志区 ──
        log_frame = tb.Labelframe(self._window, text="实时日志", padding=4)
        log_frame.pack(fill="both", expand=True, padx=10, pady=4)

        self._log_area = scrolledtext.ScrolledText(
            log_frame, font=("Consolas", 10),
            bg="#1b1b1b", fg="#a5d6a7",
            insertbackground="#a5d6a7"
        )
        self._log_area.pack(fill="both", expand=True)

        # ── 按钮区 ──
        btn_frame = tb.Frame(self._window, padding=8)
        btn_frame.pack(fill="x", padx=10)

        self._btn_start = RoundedButton(btn_frame, text="▶ 开始扫描",
                                       command=self._start_scan, width=130, height=38,
                                       bg_color="#0d6efd", fg_color="#ffffff",
                                       hover_color="#0b5ed7", radius=12)
        self._btn_start.pack(side="left", padx=3)

        self._btn_pause = RoundedButton(btn_frame, text="⏸ 暂停",
                                       command=self._toggle_pause, width=100, height=38,
                                       bg_color="#ffc107", fg_color="#212529",
                                       hover_color="#e0a800", radius=12)
        self._btn_pause.pack(side="left", padx=3)
        self._btn_pause.configure(state="disabled")

        self._btn_stop = RoundedButton(btn_frame, text="⏹ 停止",
                                      command=self._stop_scan, width=100, height=38,
                                      bg_color="#dc3545", fg_color="#ffffff",
                                      hover_color="#c82333", radius=12)
        self._btn_stop.pack(side="left", padx=3)
        self._btn_stop.configure(state="disabled")

        RoundedButton(btn_frame, text="重建FAISS索引",
                     command=self._rebuild_faiss, width=140, height=38,
                     bg_color="#6f42c1", fg_color="#ffffff",
                     hover_color="#5a32a3", radius=12).pack(side="right", padx=3)

        RoundedButton(btn_frame, text="清除日志",
                     command=lambda: self._log_area.delete("1.0", "end"),
                     width=100, height=38, bg_color="#e0e0e0",
                     fg_color="#212529", hover_color="#d0e0ff",
                     radius=10).pack(side="right", padx=3)

    # ═══════════════════════════════════════════════
    # 日志系统 (线程安全)
    # ═══════════════════════════════════════════════

    def _log(self, msg: str):
        """线程安全日志 — 放入队列，由UI线程轮询显示"""
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_queue.put(f"[{ts}] {msg}")

    def _poll_log(self):
        """UI线程定期检查日志队列并更新界面"""
        try:
            while True:
                msg = self._log_queue.get_nowait()
                self._log_area.insert("end", msg + "\n")
                self._log_area.see("end")
        except queue.Empty:
            pass

        try:
            while True:
                prog_data = self._progress_queue.get_nowait()
                self._apply_progress(prog_data)
        except queue.Empty:
            pass

        self._window.after(100, self._poll_log)

    def _apply_progress(self, data: dict):
        """应用进度更新到UI"""
        if "total_videos" in data:
            self._total_videos = data["total_videos"]
            self._stat_total.set(f"总视频: {self._total_videos:,}")
            self._progress_bar["maximum"] = max(1, self._total_videos)

        if "scanned" in data:
            self._scanned_count = data["scanned"]
            self._stat_scanned.set(f"已扫描: {self._scanned_count:,}")
            self._progress_bar["value"] = min(self._scanned_count, self._progress_bar.get("maximum", 1))

        if "island_found" in data:
            self._island_found = data["island_found"]
            self._stat_island.set(f"岛台帧: {self._island_found:,}")

        if "saved" in data:
            self._saved_count = data["saved"]
            self._stat_saved.set(f"入库: {self._saved_count:,}")

        if "current_file" in data:
            self._current_file_var.set(data["current_file"])

        if "elapsed" in data:
            self._stat_elapsed.set(f"耗时: {data['elapsed']}")

    # ═══════════════════════════════════════════════
    # 路径选择
    # ═══════════════════════════════════════════════

    def _choose_path(self):
        """选择扫描路径"""
        path = filedialog.askdirectory(title="选择素材文件夹")
        if path:
            self.scan_paths = [path]
            self._path_var.set(path)
            self._log(f"已选择扫描路径: {path}")
        else:
            # 用户取消
            pass

    def _estimate_video_count(self):
        """估算全盘视频数量"""
        def _estimate():
            try:
                from core.video_scanner import count_videos_in_dir, get_all_drives
                paths = self.scan_paths if self.scan_paths else get_all_drives()
                self._log("正在估算视频总数（这可能需要一些时间）...")
                count = count_videos_in_dir(paths, max_count=50000)
                self._progress_queue.put({"total_videos": count})
                self._log(f"预估发现 ~{count:,} 个视频文件")
                self._progress_queue.put({"scanned": 0})
            except Exception as e:
                self._log(f"估算失败: {e}")

        threading.Thread(target=_estimate, daemon=True).start()

    # ═══════════════════════════════════════════════
    # 扫描控制
    # ═══════════════════════════════════════════════

    def _start_scan(self):
        """开始/继续扫描"""
        if self._running and self._paused:
            # 继续
            self._paused = False
            self._pause_event.set()
            self._btn_pause.configure(text="⏸ 暂停")
            self._log("▶ 扫描已继续")
            return

        if self._running:
            return

        self._running = True
        self._paused = False
        self._cancel_event.clear()
        self._pause_event.set()  # 初始不暂停

        self._start_time = time.time()
        self._scanned_count = 0
        self._island_found = 0
        self._saved_count = 0

        self._log_area.delete("1.0", "end")
        self._log("=" * 50)
        self._log("  树剪 AI 全盘素材扫描分析开始")
        self._log(f"  抽帧间隔: {self._frame_interval.get()}s")
        self._log(f"  并发数: {self._max_workers.get()}")
        self._log(f"  跳过已分析: {'是' if self._skip_analyzed.get() else '否'}")
        self._log("=" * 50)

        self._btn_start.pack_forget()
        self._btn_start = RoundedButton(
            self._btn_start.master, text="▶ 开始扫描",
            command=self._start_scan, width=130, height=38,
            bg_color="#0d6efd", fg_color="#ffffff",
            hover_color="#0b5ed7", radius=12)
        self._btn_start.configure(state="disabled")
        # Re-pack at the same position
        self._btn_start.pack_forget()
        self._btn_start.pack(side="left", padx=3, before=self._btn_pause)
        self._btn_start.configure(state="disabled")

        self._btn_pause.configure(state="normal")
        self._btn_stop.configure(state="normal")
        self._progress_bar["value"] = 0

        # 启动后台扫描线程
        self._scanner_thread = threading.Thread(
            target=self._scan_thread_main, daemon=True
        )
        self._scanner_thread.start()

    def _toggle_pause(self):
        """暂停/继续"""
        if not self._running:
            return
        if self._paused:
            # 继续
            self._paused = False
            self._pause_event.set()
            self._btn_pause.configure(text="⏸ 暂停")
            self._log("▶ 扫描已继续")
        else:
            # 暂停
            self._paused = True
            self._pause_event.clear()
            self._btn_pause.configure(text="▶ 继续")
            self._log("⏸ 扫描已暂停")

    def _stop_scan(self):
        """停止扫描"""
        self._cancel_event.set()
        self._pause_event.set()  # 如果正在暂停，先恢复以便退出
        self._running = False
        self._paused = False
        self._btn_start.configure(state="normal")
        self._btn_pause.configure(state="disabled")
        self._btn_stop.configure(state="disabled")
        self._log("⏹ 扫描已停止")

    # ═══════════════════════════════════════════════
    # 扫描主线程
    # ═══════════════════════════════════════════════

    def _scan_thread_main(self):
        """后台扫描主流程"""
        try:
            from core.video_scanner import (
                iter_all_videos, get_all_drives,
                DEFAULT_EXCLUDE_DIRS, DEFAULT_VIDEO_EXTENSIONS,
                load_scan_checkpoint, save_scan_checkpoint, clear_scan_checkpoint,
                get_video_file_info, count_videos_in_dir,
            )
            from core.smart_analyzer import get_analyzer
            from core.library_builder import LibraryBuilder
        except Exception as e:
            self._log(f"❌ 模块加载失败: {e}")
            self._stop_scan()
            return

        # 确定扫描路径
        paths = self.scan_paths
        if not paths:
            paths = get_all_drives()
            self._log(f"全盘扫描: {', '.join(paths)}")

        # 估算总数
        self._log("正在估算视频总数...")
        total = count_videos_in_dir(paths, max_count=50000)
        self._progress_queue.put({"total_videos": total})
        self._log(f"预估总数: ~{total:,} 个视频")

        # 创建分析器
        analyzer = get_analyzer(max_workers=self._max_workers.get())
        analyzer.reset_cancel()
        frame_interval = self._frame_interval.get()

        # 加载已分析列表
        lb = LibraryBuilder()
        skip_analyzed = self._skip_analyzed.get()

        # 遍历视频
        scanned = 0
        pending_batch = []
        BATCH_SIZE = 10  # 每批10个视频

        checkpoint = load_scan_checkpoint()
        last_path = checkpoint.get("last_path")

        try:
            for video_path in iter_all_videos(
                root_paths=paths,
                exclude_dirs=DEFAULT_EXCLUDE_DIRS,
                cancel_event=self._cancel_event,
            ):
                # 暂停检查
                if not self._pause_event.is_set():
                    self._log("⏸ 等待恢复...")
                    self._pause_event.wait()

                # 取消检查
                if self._cancel_event.is_set():
                    self._log("⏹ 收到停止信号")
                    break

                # 跳过已分析
                if skip_analyzed:
                    try:
                        pending = lb.get_pending_videos([video_path])
                        if not pending:  # 无变化，跳过
                            scanned += 1
                            continue
                    except Exception:
                        pass

                # 检查文件大小
                info = get_video_file_info(video_path)
                max_mb = float(os.environ.get("TREECUT_SCAN_MAX_VIDEO_SIZE_MB", "500"))
                if info.get("size_mb", 0) > max_mb:
                    self._log(f"⏭ 跳过大型视频: {Path(video_path).name} ({info['size_mb']:.0f}MB)")
                    scanned += 1
                    continue

                pending_batch.append(video_path)

                # 达到批次大小，开始分析
                if len(pending_batch) >= BATCH_SIZE:
                    scanned += self._process_batch(
                        pending_batch, analyzer, frame_interval, lb
                    )
                    pending_batch = []

                # 更新进度
                if scanned % 50 == 0:
                    elapsed = time.time() - self._start_time if self._start_time else 0
                    elapsed_str = f"{int(elapsed//60)}分{int(elapsed%60)}秒"
                    self._progress_queue.put({
                        "scanned": scanned,
                        "elapsed": elapsed_str,
                    })
                    save_scan_checkpoint(video_path, scanned, self._saved_count)

                # 定期更新UI总视频数
                if scanned > total:
                    total = scanned + 100  # 动态扩展
                    self._progress_queue.put({"total_videos": total})

            # 处理最后一批
            if pending_batch and not self._cancel_event.is_set():
                scanned += self._process_batch(
                    pending_batch, analyzer, frame_interval, lb
                )

            # 完成
            elapsed = time.time() - self._start_time if self._start_time else 0
            elapsed_str = f"{int(elapsed//60)}分{int(elapsed%60)}秒"
            self._progress_queue.put({
                "scanned": scanned,
                "elapsed": elapsed_str,
            })

            self._log("=" * 50)
            self._log(f"✅ 扫描完成！")
            self._log(f"   扫描视频: {scanned:,}")
            self._log(f"   发现岛台帧: {self._island_found:,}")
            self._log(f"   入库记录: {self._saved_count:,}")
            self._log(f"   总耗时: {elapsed_str}")
            self._log("=" * 50)
            self._log("💡 提示：新入库的素材将在下次生成时自动被检索到")
            self._log("💡 如需立即生效，请点击「重建FAISS索引」按钮")

            clear_scan_checkpoint()

        except Exception as e:
            self._log(f"❌ 扫描异常: {e}")
            import traceback
            self._log(traceback.format_exc())

        finally:
            self._window.after(0, lambda: (
                self._btn_start.configure(state="normal"),
                self._btn_pause.configure(state="disabled"),
                self._btn_stop.configure(state="disabled"),
            ))
            self._running = False

    def _process_batch(
        self, video_paths: list, analyzer, frame_interval: float, lb: object
    ) -> int:
        """处理一批视频（帧级别），返回实际扫描数"""
        scanned = 0
        for vp in video_paths:
            if self._cancel_event.is_set():
                break
            if not self._pause_event.is_set():
                self._pause_event.wait()

            try:
                fname = Path(vp).name
                self._progress_queue.put({
                    "current_file": f"分析: {fname[:80]}"
                })

                # v11.3: 使用帧级分析
                def _frame_callback(frame_data):
                    """每帧分析完成 → 推送到素材库标签页"""
                    if self._library_tab:
                        try:
                            self._library_tab.add_frame_from_scanner(frame_data)
                        except Exception:
                            pass

                result = analyzer.analyze_video_frames(
                    vp, frame_interval=frame_interval,
                    on_frame_callback=_frame_callback,
                    log_callback=self._log
                )

                # 视频分析完成 → 批量推送到素材库
                if self._library_tab and result.get("frames_data"):
                    try:
                        self._library_tab.add_video_frames_batch(
                            vp, result["frames_data"]
                        )
                    except Exception:
                        pass

                scanned += 1
                island = result.get("island_frames", 0)
                total_frames = result.get("total_frames", 0)
                self._island_found += island
                self._saved_count += result.get("saved_frames", 0)

                self._progress_queue.put({
                    "scanned": self._scanned_count + scanned,
                    "island_found": self._island_found,
                    "saved": self._saved_count,
                })

                self._scanned_count += 1

                # 标记已分析
                try:
                    lb.mark_video_analyzed(vp)
                except Exception:
                    pass

            except Exception as e:
                self._log(f"⚠ {fname[:60]}: {e}")
                scanned += 1

        return scanned

    # ═══════════════════════════════════════════════
    # 其他操作
    # ═══════════════════════════════════════════════

    def _rebuild_faiss(self):
        """重建FAISS索引"""
        if self._running and not self._paused:
            if not messagebox.askyesno("提示", "扫描进行中，重建索引可能需要较长时间且会消耗大量资源。是否继续？"):
                return

        self._log("🔧 开始重建FAISS索引...")
        self._btn_start.configure(state="disabled")

        def _rebuild():
            try:
                from core.library_builder import LibraryBuilder
                lb = LibraryBuilder()
                lb.build_faiss_index(
                    progress=lambda msg: self._log(f"   {msg}")
                )
                self._log("✅ FAISS索引重建完成")
            except Exception as e:
                self._log(f"❌ 重建失败: {e}")

        threading.Thread(target=_rebuild, daemon=True).start()

    def _on_close(self):
        """关闭窗口"""
        if self._running:
            if messagebox.askyesno("确认", "扫描正在进行中，确定要停止并关闭吗？"):
                self._stop_scan()
            else:
                return
        self._window.destroy()

    def show(self):
        """显示窗口并进入消息循环"""
        self._window.mainloop()

    def wait_window(self):
        """等待窗口关闭"""
        self._window.wait_window()
