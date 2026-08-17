"""
ScriptInputArea — 批量粘贴 + 智能识别组件
用法:
  area = ScriptInputArea(parent, on_scripts_parsed=callback)
  scripts = area.get_scripts()
"""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, List


class ScriptInputArea(ttk.Frame):
    """多行文本输入 + 识别并填充 + 强制按行复选框"""

    def __init__(self, parent, on_scripts_parsed: Callable = None, **kwargs):
        super().__init__(parent, **kwargs)
        self._on_parsed = on_scripts_parsed

        ttk.Label(self, text="从Excel粘贴(自动识别):", font=("", 11, "bold")).pack(anchor="w")
        self._text = tk.Text(self, height=4, font=("Microsoft YaHei", 11),
                             bg="#2a2a3c", fg="#e8eaf6")
        self._text.pack(fill="x", pady=2)

        ctrl = ttk.Frame(self)
        ctrl.pack(fill="x", pady=4)
        ttk.Button(ctrl, text="识别并填充", command=self._do_parse).pack(side="left", padx=3)
        ttk.Button(ctrl, text="清空", command=lambda: self._text.delete("1.0","end")).pack(side="left", padx=3)
        self._force_line = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="强制按行", variable=self._force_line).pack(side="left", padx=6)

        self._status = ttk.Label(ctrl, text="", foreground="#8892b0")
        self._status.pack(side="left", padx=10)

    def _do_parse(self):
        raw = self._text.get("1.0", "end-1c")
        from core.script_utils import split_scripts
        scripts = split_scripts(raw, force_by_line=self._force_line.get())
        if not scripts:
            messagebox.showinfo("提示", "未识别到有效文案。\n用空行分隔不同脚本，或勾选「强制按行」。")
            return
        self._status.config(text=f"识别 {len(scripts)} 条")
        if self._on_parsed:
            self._on_parsed(scripts)

    def get_scripts(self) -> List[str]:
        from core.script_utils import split_scripts
        return split_scripts(self._text.get("1.0", "end-1c"),
                             force_by_line=self._force_line.get())

    def clear(self):
        self._text.delete("1.0", "end")
        self._status.config(text="")
