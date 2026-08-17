"""
树剪 — 静默子进程工具
所有 subprocess 调用统一使用此模块，Windows 下不会弹出命令行窗口。
"""
import os, subprocess


def _win_flags():
    """Windows 下隐藏窗口标志"""
    if os.name == 'nt':
        si = subprocess.STARTUPINFO()
        si.dwFlags = subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return si, subprocess.CREATE_NO_WINDOW
    return None, 0


def run(cmd, **kwargs):
    """静默 subprocess.run — 等价于 subprocess.run 但 Windows 不弹窗"""
    if os.name == 'nt':
        si, cf = _win_flags()
        kwargs.setdefault('startupinfo', si)
        kwargs.setdefault('creationflags', cf)
    return subprocess.run(cmd, **kwargs)


def call(cmd, **kwargs):
    """静默 subprocess.call"""
    if os.name == 'nt':
        si, cf = _win_flags()
        kwargs.setdefault('startupinfo', si)
        kwargs.setdefault('creationflags', cf)
    return subprocess.call(cmd, **kwargs)


def check_call(cmd, **kwargs):
    """静默 subprocess.check_call"""
    if os.name == 'nt':
        si, cf = _win_flags()
        kwargs.setdefault('startupinfo', si)
        kwargs.setdefault('creationflags', cf)
    return subprocess.check_call(cmd, **kwargs)


def Popen(cmd, **kwargs):
    """静默 subprocess.Popen"""
    if os.name == 'nt':
        si, cf = _win_flags()
        kwargs.setdefault('startupinfo', si)
        kwargs.setdefault('creationflags', cf)
    return subprocess.Popen(cmd, **kwargs)
