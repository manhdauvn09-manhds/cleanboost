"""Đảm bảo chỉ 1 bản CleanBoost GUI chạy tại 1 thời điểm.

Kể cả khi bản cũ chạy quyền User và bản mới chạy quyền Admin (hoặc ngược
lại): khi phát hiện bản cũ, app hỏi user có muốn tắt bản cũ để mở bản mới
không. Chọn "Có" -> tắt bản cũ, mở bản mới. Chọn "Không" -> thoát.

Cơ chế: lock file chứa PID trong thư mục dữ liệu của user hiện tại.
"""
import atexit
import os
import sys


def _lock_path() -> str:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "CleanBoost")
    else:
        d = os.path.join(os.path.expanduser("~"), ".local",
                         "share", "cleanboost")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "instance.lock")


def _read_lock():
    try:
        with open(_lock_path(), encoding="utf-8") as f:
            pid = int(f.read().strip())
            return pid if pid > 0 else None
    except (OSError, ValueError):
        return None


def _write_lock(pid: int):
    try:
        with open(_lock_path(), "w", encoding="utf-8") as f:
            f.write(str(pid))
    except OSError:
        pass


def _clear_lock():
    try:
        if _read_lock() == os.getpid():
            os.remove(_lock_path())
    except OSError:
        pass


def _looks_like_us(pid: int):
    """True: chắc chắn là CleanBoost. False: chắc chắn không phải.
    None: không đọc được thông tin (thường là process quyền cao hơn)."""
    import psutil
    try:
        p = psutil.Process(pid)
        cmd = " ".join(p.cmdline()).lower()
        name = (p.name() or "").lower()
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return None
    if "gui.py" in cmd:
        return True
    if name == "cleanboost.exe":
        return True
    return False


def _priv_hint(pid: int) -> str:
    """Đoán quyền của process cũ (để hiển thị cho user)."""
    import psutil
    try:
        psutil.Process(pid).cmdline()
        return "User"
    except psutil.AccessDenied:
        return "Admin (có thể)"
    except psutil.NoSuchProcess:
        return "?"


def _kill_old(pid: int):
    """Trả về (ok, message)."""
    import psutil
    try:
        p = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return True, "Bản cũ đã tự thoát."
    try:
        p.terminate()
        try:
            p.wait(timeout=6)
        except psutil.TimeoutExpired:
            p.kill()
            p.wait(timeout=6)
        return True, "Đã tắt bản cũ."
    except psutil.AccessDenied:
        return False, ("Không thể tắt bản cũ vì nó đang chạy với quyền cao hơn "
                       "(Admin).\nHãy chuột phải bản mới -> Run as administrator, "
                       "hoặc tắt bản cũ thủ công rồi mở lại.")
    except psutil.NoSuchProcess:
        return True, "Bản cũ đã tự thoát."
    except Exception as e:  # noqa: BLE001
        return False, f"Không tắt được bản cũ: {e}"


def ensure_single_instance() -> bool:
    """Kiểm tra trước khi mở GUI.

    Trả về True nếu được chạy tiếp, False nếu phải thoát ngay.
    Tự hiện hộp thoại hỏi user khi phát hiện bản cũ.
    """
    import psutil
    import tkinter as tk
    from tkinter import messagebox

    me = os.getpid()
    other = _read_lock()
    if other and other != me and psutil.pid_exists(other):
        looks = _looks_like_us(other)
        if looks is not False:
            priv = _priv_hint(other)
            root = tk.Tk()
            root.withdraw()
            try:
                ans = messagebox.askyesno(
                    "CleanBoost đang chạy",
                    f"Đã phát hiện 1 bản CleanBoost khác đang chạy\n"
                    f"(PID {other}, quyền {priv}).\n\n"
                    "Bạn có muốn TẮT bản cũ để mở bản mới không?\n\n"
                    "• Có: tắt bản cũ, mở bản mới\n"
                    "• Không: giữ bản cũ, không mở thêm",
                    parent=root)
                if not ans:
                    return False
                ok, msg = _kill_old(other)
                if not ok:
                    messagebox.showerror("Không thể tắt bản cũ", msg,
                                         parent=root)
                    return False
            finally:
                try:
                    root.destroy()
                except Exception:  # noqa: BLE001
                    pass
    _write_lock(me)
    atexit.register(_clear_lock)
    return True
