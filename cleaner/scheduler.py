"""Register automatic periodic cleanup.

Windows: Task Scheduler (schtasks) — every Sunday 03:00.
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
    """Returns (ok, message). Never raises."""
    try:
        if sys.platform == "win32":
            return _install_windows()
        return _install_linux()
    except FileNotFoundError as e:
        return False, f"Missing system tool: {e.filename} — please install cron."
    except Exception as e:  # noqa: BLE001
        return False, f"Error: {e}"


def remove():
    try:
        if sys.platform == "win32":
            return _remove_windows()
        return _remove_linux()
    except FileNotFoundError as e:
        return False, f"Missing system tool: {e.filename}."
    except Exception as e:  # noqa: BLE001
        return False, f"Error: {e}"


def status():
    try:
        if sys.platform == "win32":
            r = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME],
                               capture_output=True, text=True)
            if r.returncode == 0:
                return True, f"Registered: {TASK_NAME} (Task Scheduler)."
            return False, "No automatic schedule registered."
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if r.returncode == 0 and "auto_clean.py" in r.stdout:
            return True, "Automatic cleanup scheduled in cron."
        return False, "No automatic schedule registered."
    except FileNotFoundError:
        return False, "Not registered (cron not found)."
    except Exception as e:  # noqa: BLE001
        return False, f"Error: {e}"


# ------------------------- Windows -------------------------

def _install_windows():
    root = _root()
    pyw = os.path.join(root, ".venv", "Scripts", "pythonw.exe")
    script = os.path.join(root, "auto_clean.py")
    if not os.path.exists(pyw):
        return False, "No .venv yet — run setup_windows.bat first."
    cmd = ["schtasks", "/Create", "/TN", TASK_NAME,
           "/TR", f'\\"{pyw}\\" \\"{script}\\"',
           "/SC", "WEEKLY", "/D", "SUN", "/ST", "03:00", "/F"]
    if privilege.is_admin():
        cmd += ["/RL", "HIGHEST"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0:
        extra = " (highest privileges)" if privilege.is_admin() else \
                " (re-run as Admin to clean system areas)"
        return True, f"Automatic cleanup scheduled every Sunday 03:00{extra}."
    err = (r.stderr or "").strip().splitlines()
    return False, f"schtasks failed: {err[0][:200] if err else r.returncode}"


def _remove_windows():
    r = subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
                       capture_output=True, text=True)
    if r.returncode == 0:
        return True, "Automatic schedule removed."
    return False, "No schedule found to remove."


# ------------------------- Linux -------------------------

def _install_linux():
    root = _root()
    py = os.path.join(root, ".venv", "bin", "python")
    line = (f"0 3 * * 0 {py} {root}/auto_clean.py "
            f">> {root}/auto_clean.log 2>&1")
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = r.stdout if r.returncode == 0 else ""
    if "auto_clean.py" in existing:
        return True, "Automatic cleanup is already in cron."
    new = (existing.rstrip() + "\n" + line + "\n") if existing.strip() \
        else line + "\n"
    p = subprocess.run(["crontab", "-"], input=new,
                       capture_output=True, text=True)
    if p.returncode == 0:
        return True, "Automatic cleanup scheduled every Sunday 03:00 (cron)."
    return False, f"Failed to write crontab: {(p.stderr or '').strip()[:200]}"


def _remove_linux():
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if r.returncode != 0:
        return False, "Could not read crontab."
    kept = [l for l in r.stdout.splitlines() if "auto_clean.py" not in l]
    new = "\n".join(kept) + ("\n" if kept else "")
    p = subprocess.run(["crontab", "-"], input=new,
                       capture_output=True, text=True)
    if p.returncode == 0:
        return True, "Automatic schedule removed."
    return False, "Failed to remove from crontab."
