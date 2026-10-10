"""Kiểm tra quyền Admin (Windows) / root (Linux)."""
import ctypes
import os
import sys


def is_admin() -> bool:
    """True nếu đang chạy với quyền Admin (Windows) hoặc root (Linux)."""
    try:
        if sys.platform == "win32":
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        return os.geteuid() == 0
    except Exception:
        return False


def privilege_label() -> str:
    if sys.platform == "win32":
        return "Administrator" if is_admin() else "user thường"
    return "root" if is_admin() else "user thường"
