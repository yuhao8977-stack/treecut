"""
ProgressPanel — 可复用的进度条组件
用法:
  panel = ProgressPanel(parent)
  panel.set_progress(3, 6)  # step 3 of 6
  panel.set_status("分析中...")
"""
import tkinter as tk
from tkinter import ttk


class ProgressPanel(ttk.Frame):
    """进度条 + 百分比 + 状态文字"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._bar = ttk.Progressbar(self, mode="determinate")
        self._bar.pack(fill="x", pady=2)
        self._label = ttk.Label(self, text="")
        self._label.pack()
        self._status = ttk.Label(self, text="", foreground="#8892b0")
        self._status.pack()

    def set_progress(self, step: int, total: int):
        self._bar.configure(value=step, maximum=total)
        pct = int(step / max(total, 1) * 100)
        self._label.config(text=f"{pct}%  ({step}/{total})")

    def set_status(self, text: str, color: str = "#8892b0"):
        self._status.config(text=text, foreground=color)

    def reset(self):
        self._bar.configure(value=0)
        self._label.config(text="")
        self._status.config(text="")
