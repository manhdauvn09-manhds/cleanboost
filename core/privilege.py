"""Check for Admin (Windows) / root (Linux) rights."""
import ctypes
import os
import sys


def is_admin() -> bool:
    """True when running as Admin (Windows) or root (Linux)."""
    try:
        if sys.platform == "win32":
            shell32 = ctypes.windll.shell32
            shell32.IsUserAnAdmin.restype = ctypes.c_bool  # v2.8.0
            return bool(shell32.IsUserAnAdmin())
        return os.geteuid() == 0
    except Exception:
        return False


def privilege_label() -> str:
    if sys.platform == "win32":
        return "Administrator" if is_admin() else "standard user"
    return "root" if is_admin() else "standard user"
