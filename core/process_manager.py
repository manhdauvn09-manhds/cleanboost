"""List and safely kill processes (always through the protection layer)."""
import getpass
import time

import psutil

from safety import protected

GB = 1024 ** 3


def _me() -> str:
    try:
        return getpass.getuser().lower()
    except Exception:
        return ""


def _prime_cpu():
    for p in psutil.process_iter():
        try:
            p.cpu_percent()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def list_processes(sort_by: str = "memory", limit: int = 20,
                   include_system: bool = False) -> list:
    """Process list; blocked system processes are hidden by default."""
    _prime_cpu()
    time.sleep(0.4)
    me = _me()
    rows = []
    for p in psutil.process_iter(["pid", "name", "username"]):
        try:
            info = p.info
            name = info.get("name") or ""
            user = info.get("username") or ""
            state = protected.check_process(name, info["pid"])
            if state == "block" and not include_system:
                continue
            with p.oneshot():
                rss = p.memory_info().rss
                cpu = p.cpu_percent()
            rows.append({
                "pid": info["pid"],
                "name": name,
                "user": user.split("\\")[-1],
                "mine": bool(me) and user.lower().endswith(me),
                "rss": rss,
                "cpu": cpu,
                "state": state,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    key = (lambda r: r["rss"]) if sort_by == "memory" else (lambda r: r["cpu"])
    rows.sort(key=key, reverse=True)
    return rows[:limit]


def kill_process(pid: int, force: bool = False):
    """Kill one process. Returns (ok, message). Never prompts the user here."""
    try:
        p = psutil.Process(pid)
        name = p.name() or f"PID {pid}"
    except psutil.NoSuchProcess:
        return False, "The process no longer exists."
    except psutil.AccessDenied:
        return False, "Cannot read process info (higher rights needed)."

    if protected.check_process(name, pid) == "block":
        return False, (
            f"{name} (PID {pid}) is a PROTECTED system process — "
            "refusing to kill to avoid crashing the OS."
        )
    try:
        if force:
            p.kill()
        else:
            p.terminate()  # let the app clean up itself
            try:
                p.wait(timeout=5)
            except psutil.TimeoutExpired:
                p.kill()  # stubborn -> force
        return True, f"Done {'force kill' if force else 'kill'} {name} (PID {pid})."
    except psutil.NoSuchProcess:
        return True, f"{name} (PID {pid}) has exited."
    except psutil.AccessDenied:
        return False, (
            "Access denied — run the app as Admin "
            "(Windows) / sudo (Linux) and try again."
        )


def emergency_candidates(min_rss_mb: int = 200) -> list:
    """Processes of the CURRENT USER that use lots of RAM and are unprotected.

    Dùng cho chế độ 'giải phóng RAM khẩn cấp'. Caller phải hỏi user
    xác nhận trước khi kill (trừ khi user đã dùng --yes).
    """
    rows = list_processes(sort_by="memory", limit=200, include_system=False)
    out = []
    for r in rows:
        if not r["mine"]:
            continue
        if r["rss"] < min_rss_mb * 1024 * 1024:
            continue
        if r["state"] == "block":
            continue
        out.append(r)
    return out
