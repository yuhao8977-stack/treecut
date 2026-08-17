"""
虚拟滚动框架 - 解决大量控件滚动卡顿问题
"""
import tkinter as tk
from tkinter import ttk
from typing import List, Callable, Any


class VirtualScrollFrame(tk.Frame):
    def __init__(self, parent, item_height=80, create_widget_func=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.item_height = item_height
        self.create_widget_func = create_widget_func
        self._items = []
        self._widgets = {}
        self._first_visible = 0
        self._last_visible = -1

        self.canvas = tk.Canvas(self, highlightthickness=0, bg="#1e1e2f")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.inner = tk.Frame(self.canvas, bg="#1e1e2f")
        self._win_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw", width=self.canvas.winfo_width())

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)

    def set_items(self, items: List[Any]):
        self._items = items
        # 清除旧控件
        for w in self._widgets.values():
            w.destroy()
        self._widgets.clear()
        self._update_visible()
        total_height = len(items) * self.item_height
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), total_height))

    def _update_visible(self):
        if not self._items:
            return
        y1 = self.canvas.canvasy(0)
        y2 = y1 + self.canvas.winfo_height()
        first = max(0, int(y1 // self.item_height))
        last = min(len(self._items) - 1, int(y2 // self.item_height) + 1)
        if first == self._first_visible and last == self._last_visible:
            return

        for idx in list(self._widgets.keys()):
            if idx < first or idx > last:
                self._widgets[idx].destroy()
                del self._widgets[idx]

        for idx in range(first, last + 1):
            if idx not in self._widgets:
                widget = (self.create_widget_func(self.inner, idx, self._items[idx])
                          if self.create_widget_func
                          else self._default_widget(self.inner, idx, self._items[idx]))
                widget.place(x=0, y=idx * self.item_height, width=self.inner.winfo_width(), height=self.item_height)
                self._widgets[idx] = widget

        self._first_visible, self._last_visible = first, last

    def _default_widget(self, parent, idx, data):
        frame = tk.Frame(parent, bg="#2a2a3c")
        tk.Label(frame, text=str(data), bg="#2a2a3c", fg="#e0e0e0").pack(side="left", padx=10)
        return frame

    def _on_inner_configure(self, e):
        self.canvas.itemconfig(self._win_id, width=e.width)
        self._update_visible()

    def _on_canvas_configure(self, e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_mousewheel(self, e):
        self.canvas.yview_scroll(int(-1 * (e.delta // 120)), "units")
        self._update_visible()

    def refresh_visible(self):
        self._update_visible()
