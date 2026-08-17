"""
FolderSelector — 可复用的素材文件夹选择器组件
支持: 复选框列表 + 全选/全不选 + 虚拟滚动 + 搜索
用法:
  selector = FolderSelector(parent, folders=[{"name":"A","count":5},...])
  selected = selector.get_selected()  # → ["A", "B"]
"""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Dict, Callable


class FolderSelector(ttk.LabelFrame):
    """文件夹选择器 — 可嵌入任意页面"""

    def __init__(self, parent, text: str = "素材文件夹",
                 folders: List[Dict] = None, cols: int = 4, max_height: int = 200,
                 on_change: Callable = None, **kwargs):
        super().__init__(parent, text=text, padding=4, **kwargs)
        self._folders = folders or []
        self._vars: Dict[str, tk.BooleanVar] = {}
        self._cols = cols
        self._on_change = on_change

        # 搜索框
        ctrl = ttk.Frame(self)
        ctrl.pack(fill="x", pady=2)
        ttk.Button(ctrl, text="全选", command=self._select_all).pack(side="left", padx=2)
        ttk.Button(ctrl, text="全不选", command=self._select_none).pack(side="left", padx=2)
        self._search_var = tk.StringVar()
        tk.Entry(ctrl, textvariable=self._search_var, width=15,
                bg="#2a2a3c", fg="#e8eaf6").pack(side="right", padx=2)
        self._search_var.trace_add("write", lambda *a: self._filter())

        # 可滚动 canvas
        canvas = tk.Canvas(self, height=max_height, highlightthickness=0, bg="#1a1a2e")
        sb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self._inner = tk.Frame(canvas, bg="#1a1a2e")
        self._inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        def _mw(e): canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<MouseWheel>", _mw)
        self._inner.bind("<MouseWheel>", _mw)

        self._populate()

    def _populate(self):
        self._build_checkboxes(self._folders)

    def _build_checkboxes(self, folders: List[Dict]):
        for w in self._inner.winfo_children():
            w.destroy()
        self._vars.clear()
        row, col = 0, 0
        for f in folders:
            v = tk.BooleanVar(value=True)
            self._vars[f["name"]] = v
            cb = ttk.Checkbutton(self._inner, text=f"{f['name']}({f.get('count','?')})", variable=v)
            cb.grid(row=row, column=col, sticky="w", padx=3, pady=1)
            col += 1
            if col >= self._cols:
                col = 0; row += 1

    def _select_all(self):
        for v in self._vars.values():
            v.set(True)
        self._notify()

    def _select_none(self):
        for v in self._vars.values():
            v.set(False)
        self._notify()

    def _filter(self):
        q = self._search_var.get().strip().lower()
        if not q:
            self._populate()
            return
        filtered = [f for f in self._folders if q in f["name"].lower()]
        self._build_checkboxes(filtered)

    def _notify(self):
        if self._on_change:
            self._on_change(self.get_selected())

    def set_folders(self, folders: List[Dict]):
        self._folders = folders
        self._populate()

    def get_selected(self) -> List[str]:
        return [n for n, v in self._vars.items() if v.get()]
