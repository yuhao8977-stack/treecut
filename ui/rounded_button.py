"""
树剪 TreeCut — 圆角按钮组件 (RoundedButton)
============================================
基于 Canvas 的自绘圆角矩形按钮，支持：
  - 自定义圆角半径 (radius)
  - 悬停效果 (hover_color)
  - 禁用状态 (disabled)
  - 点击回调 (command)
  - 自动文字居中

用法: from ui.rounded_button import RoundedButton
      btn = RoundedButton(parent, text="确定", command=do_ok)
      btn.pack()
"""
import tkinter as tk
from tkinter import font as tkfont


class RoundedButton(tk.Canvas):
    """圆角按钮 — 完全自定义绘制，兼容 tkinter 布局系统"""

    def __init__(self, parent, text="", command=None,
                 bg_color="#2e7d32", fg_color="#ffffff",
                 hover_color="#43a047", disabled_color="#bdbdbd",
                 radius=10, width=None, height=35,
                 font=None, **kwargs):
        self.command = command
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.hover_color = hover_color
        self.disabled_color = disabled_color
        self.radius = radius
        self._state = "normal"
        self._hover = False
        self._text = text
        self._font = font or ("Microsoft YaHei", 10)

        # Auto-width: if not specified, measure text
        if width is None:
            tf = tkfont.Font(family=self._font[0], size=self._font[1])
            text_w = tf.measure(text) + 30  # padding
            width = max(text_w, 60)

        super().__init__(parent, width=width, height=height,
                         highlightthickness=0, bd=0, **kwargs)
        self.width = width
        self.height = height

        self.bind("<Button-1>", self._on_click)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-3>", lambda e: None)  # 阻止右键菜单

        self._draw()

    def _draw(self):
        self.delete("all")

        if self._state == "disabled":
            fill = self.disabled_color
            text_fill = "#9e9e9e"
        elif self._hover:
            fill = self.hover_color
            text_fill = self.fg_color
        else:
            fill = self.bg_color
            text_fill = self.fg_color

        # 绘制圆角矩形 (使用 smooth polygon 近似)
        r = self.radius
        w, h = self.width, self.height
        pts = [
            r, 0,   w-r, 0,      # 上边
            w, 0,   w, r,        # 右上角
            w, h-r, w, h,        # 右边
            w-r, h, r, h,        # 下边
            0, h,   0, h-r,      # 左下角
            0, r,   0, 0,        # 左边
        ]
        self.create_polygon(pts, smooth=True, fill=fill, outline="")

        # 绘制文字 (居中)
        self.create_text(w//2, h//2, text=self._text,
                         fill=text_fill, font=self._font, anchor="center")

    def _on_click(self, event):
        if self._state == "normal" and self.command:
            self.command()

    def _on_release(self, event):
        pass

    def _on_enter(self, event):
        if self._state == "normal":
            self._hover = True
            self._draw()

    def _on_leave(self, event):
        self._hover = False
        self._draw()

    def config(self, **kwargs):
        if "text" in kwargs:
            self._text = kwargs["text"]
        if "state" in kwargs:
            self._state = kwargs["state"]
        if "command" in kwargs:
            self.command = kwargs["command"]
        if "bg" in kwargs or "bg_color" in kwargs:
            self.bg_color = kwargs.get("bg_color", kwargs.get("bg", self.bg_color))
        self._draw()

    def configure(self, **kwargs):
        self.config(**kwargs)

    def set_state(self, state):
        self._state = state
        self._draw()

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        self._text = value
        self._draw()


def rdbtn(parent, text="", command=None, width=100, height=32, **kw):
    """快捷工厂函数 — 返回 RoundedButton 实例"""
    return RoundedButton(parent, text=text, command=command, width=width, height=height, **kw)
