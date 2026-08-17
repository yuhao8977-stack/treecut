"""
树剪 TreeCut v12.0 — AI審核面板 (ReviewPanel)
==============================================
連接 core/review_queue.py，提供人工審核界面。
  - 顯示待審核的AI建議列表
  - 支持「通過/拒絕/編輯」操作
  - 右上角紅點提示待審核數量
  - 審核歷史記錄
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading, json
from pathlib import Path
from datetime import datetime


class ReviewPanel(ttk.Frame):
    """AI建議審核面板 — 嵌入到桌面主窗口"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._pending_count = 0
        self._auto_refresh = False
        self._refresh_interval = 30000  # 30秒自動刷新
        self._build_ui()
        self.load_pending()

    # ═══════════════════ UI構建 ═══════════════════
    def _build_ui(self):
        """構建審核面板UI"""
        # ── 頂部標題 + 紅點 ──
        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 6))

        ttk.Label(header, text="🔍 AI審核面板", font=("Microsoft YaHei", 12, "bold")) \
            .pack(side="left")

        self._badge_label = ttk.Label(header, text="0", font=("Microsoft YaHei", 10, "bold"),
                                       foreground="white", background="#d32f2f",
                                       padding=(8, 2))
        # 初始隱藏紅點
        self._badge_label.pack_forget()

        self._status_label = ttk.Label(header, text="", font=("Microsoft YaHei", 9),
                                        foreground="gray")
        self._status_label.pack(side="right", padx=6)

        # ── 待審核列表 ──
        list_frame = ttk.Frame(self)
        list_frame.pack(fill="both", expand=True)

        columns = ("col_id", "col_type", "col_source", "col_confidence", "col_time")
        self._tree = ttk.Treeview(list_frame, columns=columns, show="headings",
                                   height=8, selectmode="browse")
        for col, width, text in zip(columns, [60, 100, 80, 60, 140],
                                     ["ID", "類型", "來源", "可信度", "提交時間"]):
            self._tree.heading(col, text=text)
            self._tree.column(col, width=width, anchor="center")

        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # ── 規則內容預覽 ──
        detail_frame = ttk.LabelFrame(self, text="規則內容預覽", padding=4)
        detail_frame.pack(fill="both", expand=True, pady=(6, 0))

        self._detail_text = scrolledtext.ScrolledText(
            detail_frame, height=6, font=("Consolas", 9),
            bg="#fafafa", fg="#212121", wrap="word"
        )
        self._detail_text.pack(fill="both", expand=True)

        # ── 操作按鈕 ──
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", pady=(6, 0))

        self._approve_btn = tk.Button(
            btn_frame, text="✅ 通過並應用", font=("Microsoft YaHei", 10, "bold"),
            bg="#4caf50", fg="white", activebackground="#388e3c",
            command=self._on_approve, state="disabled", cursor="hand2",
            relief="flat", padx=12, pady=4
        )
        self._approve_btn.pack(side="left", padx=(0, 4))

        self._reject_btn = tk.Button(
            btn_frame, text="❌ 拒絕", font=("Microsoft YaHei", 10),
            bg="#f44336", fg="white", activebackground="#d32f2f",
            command=self._on_reject, state="disabled", cursor="hand2",
            relief="flat", padx=12, pady=4
        )
        self._reject_btn.pack(side="left", padx=4)

        tk.Button(
            btn_frame, text="🔄 刷新", font=("Microsoft YaHei", 9),
            command=self.load_pending, cursor="hand2",
            relief="groove", padx=10
        ).pack(side="right", padx=2)

        tk.Button(
            btn_frame, text="📋 歷史", font=("Microsoft YaHei", 9),
            command=self._show_history, cursor="hand2",
            relief="groove", padx=10
        ).pack(side="right", padx=2)

        self._current_item = None

    # ═══════════════════ 加載待審核列表 ═══════════════════
    def load_pending(self):
        """加載待審核的AI建議"""
        try:
            from core.review_queue import get_review_queue
            rq = get_review_queue()
            items = rq.get_pending(limit=50)
            self._pending_count = len(items)
            self._update_tree(items)
            self._update_badge()
            self._status_label.config(
                text=f"共 {len(items)} 條待審核" if items else "暫無待審核項"
            )
            self._start_auto_refresh()
        except ImportError:
            self._status_label.config(text="⚠ review_queue 模塊未載入")
        except Exception as e:
            self._status_label.config(text=f"載入失敗: {e}")

    def _update_tree(self, items):
        """更新 Treeview 列表"""
        for row in self._tree.get_children():
            self._tree.delete(row)
        for item in items:
            rid = item.get("id", "?")
            rtype = item.get("rule_type", "?")
            source = item.get("source", "AI")
            conf = item.get("confidence", 0)
            ts = item.get("created_at", "")[:19] if item.get("created_at") else "?"
            self._tree.insert("", "end", iid=str(rid),
                              values=(rid, rtype, source, f"{conf:.0%}", ts))

    def _update_badge(self):
        """更新紅點徽標"""
        if self._pending_count > 0:
            self._badge_label.config(text=str(self._pending_count))
            self._badge_label.pack(side="left", padx=6)
        else:
            self._badge_label.pack_forget()

    def _start_auto_refresh(self):
        """啟動自動刷新"""
        if self._auto_refresh:
            return
        self._auto_refresh = True

        def _loop():
            while self._auto_refresh:
                import time
                time.sleep(self._refresh_interval / 1000.0)
                if self._auto_refresh and self.winfo_exists():
                    self.after(0, self.load_pending)

        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    def stop_auto_refresh(self):
        self._auto_refresh = False

    # ═══════════════════ 選中處理 ═══════════════════
    def _on_select(self, event):
        """選中列表項 — 顯示詳情"""
        sel = self._tree.selection()
        if not sel:
            self._approve_btn.config(state="disabled")
            self._reject_btn.config(state="disabled")
            self._detail_text.delete("1.0", "end")
            self._current_item = None
            return

        self._current_item = sel[0]
        self._approve_btn.config(state="normal")
        self._reject_btn.config(state="normal")

        # 獲取詳情
        try:
            from core.review_queue import get_review_queue
            rq = get_review_queue()
            items = rq.get_pending(limit=50)
            for item in items:
                if str(item.get("id")) == self._current_item:
                    content = item.get("content", {})
                    self._detail_text.delete("1.0", "end")
                    self._detail_text.insert("1.0",
                        json.dumps(content, ensure_ascii=False, indent=2))
                    return
        except Exception as e:
            self._detail_text.delete("1.0", "end")
            self._detail_text.insert("1.0", f"(載入失敗: {e})")

    # ═══════════════════ 通過/拒絕 ═══════════════════
    def _on_approve(self):
        if not self._current_item:
            return
        rid = int(self._current_item)
        if not messagebox.askyesno("確認通過",
                                    f"確定通過審核ID={rid}的規則？\n\n通過後將自動應用到系統中。"):
            return
        try:
            from core.review_queue import get_review_queue
            rq = get_review_queue()
            ok = rq.approve(rid, reviewer="操作員")
            if ok:
                messagebox.showinfo("成功", f"審核ID={rid} 已通過並應用！")
                self.load_pending()
            else:
                messagebox.showerror("失敗", "審核失敗，可能已處理或規則無效。")
        except Exception as e:
            messagebox.showerror("錯誤", f"審核異常: {e}")

    def _on_reject(self):
        if not self._current_item:
            return
        rid = int(self._current_item)
        note = tk.simpledialog.askstring("拒絕原因", "請輸入拒絕原因（可選）:",
                                          parent=self)
        if note is None:
            return  # 用戶取消
        try:
            from core.review_queue import get_review_queue
            rq = get_review_queue()
            rq.reject(rid, note or "人工拒絕")
            messagebox.showinfo("已拒絕", f"審核ID={rid} 已拒絕。")
            self.load_pending()
        except Exception as e:
            messagebox.showerror("錯誤", f"操作異常: {e}")

    # ═══════════════════ 歷史記錄 ═══════════════════
    def _show_history(self):
        """顯示審核歷史彈窗"""
        try:
            from core.review_queue import get_review_queue
            rq = get_review_queue()
            history = rq.get_history(limit=30)

            win = tk.Toplevel(self)
            win.title("審核歷史記錄")
            win.geometry("700x450")

            columns = ("h_id", "h_type", "h_status", "h_reviewer", "h_time")
            tree = ttk.Treeview(win, columns=columns, show="headings")
            for col, w, text in zip(columns, [50, 120, 80, 80, 140],
                                     ["ID", "類型", "狀態", "審核人", "審核時間"]):
                tree.heading(col, text=text)
                tree.column(col, width=w, anchor="center")

            for h in history:
                tree.insert("", "end", values=(
                    h.get("id"), h.get("rule_type"),
                    h.get("status"), h.get("reviewer") or "-",
                    (h.get("reviewed_at") or h.get("created_at", ""))[:19]
                ))

            vsb = ttk.Scrollbar(win, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)
            vsb.pack(side="right", fill="y")
        except Exception as e:
            messagebox.showerror("錯誤", f"無法加載歷史: {e}")


# ════════════════════════════════════════════════════════
# 快速接入: 桌面主窗口用法
# ════════════════════════════════════════════════════════
def create_review_panel(parent) -> ReviewPanel:
    """
    在桌面主窗口中創建審核面板。

    用法 (在 desktop.py 中):
        from ui.review_panel import create_review_panel
        self._review_panel = create_review_panel(some_notebook_frame)
        # 添加到某個notebook tab中
    """
    panel = ReviewPanel(parent)
    return panel


if __name__ == "__main__":
    # 獨立測試
    root = tk.Tk()
    root.title("審核面板測試")
    root.geometry("600x500")
    panel = create_review_panel(root)
    panel.pack(fill="both", expand=True, padx=10, pady=10)
    root.mainloop()
