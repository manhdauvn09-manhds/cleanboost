"""Ensure only one CleanBoost GUI instance runs at a time.

Even when the old instance runs as User and the new one as Admin (or vice
versa): when an old instance is found, the app asks whether to close the
old one and open the new one. "Yes" closes the old and opens the new;
"No" exits.

Mechanism: a lock file holding the PID in the current user's data dir.
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
    """Returns (pid, create_time) or (None, None)."""
    try:
        with open(_lock_path(), encoding="utf-8") as f:
            parts = f.read().strip().split()
            pid = int(parts[0])
            ctime = float(parts[1]) if len(parts) > 1 else None
            return (pid, ctime) if pid > 0 else (None, None)
    except (OSError, ValueError, IndexError):
        return None, None


def _write_lock(pid: int):
    import psutil
    try:
        ctime = psutil.Process(pid).create_time()
    except Exception:  # noqa: BLE001
        ctime = 0
    try:
        with open(_lock_path(), "w", encoding="utf-8") as f:
            f.write(f"{pid} {ctime}")
    except OSError:
        pass


def _clear_lock():
    try:
        pid, _ctime = _read_lock()
        if pid == os.getpid():
            os.remove(_lock_path())
    except OSError:
        pass


def _looks_like_us(pid: int):
    """True: definitely CleanBoost. False: definitely not.
    None: cannot read info (usually a higher-privilege process)."""
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
    """Guess the old process' rights (to show the user)."""
    import psutil
    try:
        psutil.Process(pid).cmdline()
        return "User"
    except psutil.AccessDenied:
        return "Admin (likely)"
    except psutil.NoSuchProcess:
        return "?"


def _kill_old(pid: int):
    """Returns (ok, message)."""
    import psutil
    try:
        p = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return True, "The old instance already exited."
    try:
        p.terminate()
        try:
            p.wait(timeout=6)
        except psutil.TimeoutExpired:
            p.kill()
            p.wait(timeout=6)
        return True, "Old instance closed."
    except psutil.AccessDenied:
        return False, ("Cannot close the old instance: it runs with higher rights "
                       "(Admin).\nRight-click the new launcher -> Run as administrator, "
                       "or close the old instance manually first.")
    except psutil.NoSuchProcess:
        return True, "The old instance already exited."
    except Exception as e:  # noqa: BLE001
        return False, f"Could not close the old instance: {e}"


def ensure_single_instance() -> bool:
    """Check before opening the GUI.

    Returns True to continue, False to exit immediately.
    Shows a dialog asking the user when an old instance is found.
    """
    import psutil
    import tkinter as tk
    from tkinter import messagebox

    me = os.getpid()
    other, other_ctime = _read_lock()
    if other and other != me and psutil.pid_exists(other):
        # Anti PID-reuse: create_time must match the lock write time
        try:
            cur_ctime = psutil.Process(other).create_time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            cur_ctime = None
        if other_ctime and cur_ctime and abs(cur_ctime - other_ctime) > 2:
            other = None  # PID was reused -> stale lock, ignore
    if other and other != me and psutil.pid_exists(other):
        looks = _looks_like_us(other)
        if looks is not False:
            priv = _priv_hint(other)
            # v2.5.2: when the process cannot be verified as CleanBoost
            # (looks is None — usually higher-privilege), say so plainly
            # so the user only confirms a kill they actually started.
            verify_note = ("\n(Could not verify this is CleanBoost — only "
                           "proceed if you started it.)"
                           if looks is None else "")
            root = tk.Tk()
            root.withdraw()
            try:
                ans = messagebox.askyesno(
                    "CleanBoost is already running",
                    f"Another CleanBoost instance is already running\n"
                    f"(PID {other}, rights: {priv}).{verify_note}\n\n"
                    "Close the old instance and open a new one?\n\n"
                    "• Yes: close the old, open the new\n"
                    "• No: keep the old, do not open another",
                    parent=root)
                if not ans:
                    return False
                ok, msg = _kill_old(other)
                if not ok:
                    messagebox.showerror("Cannot close old instance", msg,
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
