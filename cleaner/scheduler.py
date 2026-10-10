"""Đăng ký dọn tự động định kỳ.

Windows: Task Scheduler (schtasks) — mỗi Chủ nhật 03:00.
Linux: cron — 0 3 * * 0.
"""
import os
import subprocess
import sys

from core import privilege

TASK_NAME = "CleanBoost Weekly Clean"


def _root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def install():
    """Trả về (ok, message). Không bao giờ raise."""
    try:
        if sys.platform == "win32":
            return _install_windows()
        return _install_linux()
    except FileNotFoundError as e:
        return False, f"Thiếu công cụ hệ thống: {e.filename} — hãy cài cron."
    except Exception as e:  # noqa: BLE001
        return False, f"Lỗi: {e}"


def remove():
    try:
        if sys.platform == "win32":
            return _remove_windows()
        return _remove_linux()
    except FileNotFoundError as e:
        return False, f"Thiếu công cụ hệ thống: {e.filename}."
    except Exception as e:  # noqa: BLE001
        return False, f"Lỗi: {e}"


def status():
    try:
        if sys.platform == "win32":
            r = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME],
                               capture_output=True, text=True)
            if r.returncode == 0:
                return True, f"Đã đăng ký: {TASK_NAME} (Task Scheduler)."
            return False, "Chưa đăng ký lịch dọn tự động."
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if r.returncode == 0 and "auto_clean.py" in r.stdout:
            return True, "Đã đăng ký lịch dọn tự động trong cron."
        return False, "Chưa đăng ký lịch dọn tự động."
    except FileNotFoundError:
        return False, "Chưa đăng ký (không tìm thấy cron)."
    except Exception as e:  # noqa: BLE001
        return False, f"Lỗi: {e}"


# ------------------------- Windows -------------------------

def _install_windows():
    root = _root()
    pyw = os.path.join(root, ".venv", "Scripts", "pythonw.exe")
    script = os.path.join(root, "auto_clean.py")
    if not os.path.exists(pyw):
        return False, "Chưa có .venv — chạy setup_windows.bat trước."
    cmd = ["schtasks", "/Create", "/TN", TASK_NAME,
           "/TR", f'\\"{pyw}\\" \\"{script}\\"',
           "/SC", "WEEKLY", "/D", "SUN", "/ST", "03:00", "/F"]
    if privilege.is_admin():
        cmd += ["/RL", "HIGHEST"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0:
        extra = " (quyền cao nhất)" if privilege.is_admin() else \
                " (chạy lại bằng Admin để dọn được chỗ cần quyền hệ thống)"
        return True, f"Đã đăng ký dọn tự động mỗi Chủ nhật 03:00{extra}."
    err = (r.stderr or "").strip().splitlines()
    return False, f"schtasks thất bại: {err[0][:200] if err else r.returncode}"


def _remove_windows():
    r = subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
                       capture_output=True, text=True)
    if r.returncode == 0:
        return True, "Đã gỡ lịch dọn tự động."
    return False, "Không tìm thấy lịch để gỡ."


# ------------------------- Linux -------------------------

def _install_linux():
    root = _root()
    py = os.path.join(root, ".venv", "bin", "python")
    line = (f"0 3 * * 0 {py} {root}/auto_clean.py "
            f">> {root}/auto_clean.log 2>&1")
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = r.stdout if r.returncode == 0 else ""
    if "auto_clean.py" in existing:
        return True, "Đã có lịch dọn tự động trong cron."
    new = (existing.rstrip() + "\n" + line + "\n") if existing.strip() \
        else line + "\n"
    p = subprocess.run(["crontab", "-"], input=new,
                       capture_output=True, text=True)
    if p.returncode == 0:
        return True, "Đã đăng ký dọn tự động mỗi Chủ nhật 03:00 (cron)."
    return False, f"Ghi crontab thất bại: {(p.stderr or '').strip()[:200]}"


def _remove_linux():
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if r.returncode != 0:
        return False, "Không đọc được crontab."
    kept = [l for l in r.stdout.splitlines() if "auto_clean.py" not in l]
    new = "\n".join(kept) + ("\n" if kept else "")
    p = subprocess.run(["crontab", "-"], input=new,
                       capture_output=True, text=True)
    if p.returncode == 0:
        return True, "Đã gỡ lịch dọn tự động."
    return False, "Gỡ crontab thất bại."
