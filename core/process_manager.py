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


def snapshot_pids_by_name(name: str) -> set:
    """PIDs of currently running processes with this exe name (v2.8.0).

    Taken BEFORE a kill: any same-name PID alive afterwards that was
    NOT in this set is a respawn, not a pre-existing second instance.
    (Comparing create_time against time.time() proved unreliable —
    psutil's clock basis can skew against wall time.)
    """
    want = (name or "").lower()
    out = set()
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if (p.info.get("name") or "").lower() == want:
                out.add(p.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out


def verify_process_gone(pid: int, name: str, known_pids=None,
                        timeout: float = 3.0):
    """After a kill, check what REALLY happened (v2.8.0).

    Some apps (OneDrive is the classic case) restart themselves the
    moment they are killed, so "Closed 1/1" was a lie: the user saw
    the app still in the list and concluded the kill button was
    broken. known_pids is the snapshot from before the kill.
    Returns (state, new_pid):
    - "gone": the PID is gone and no NEW same-name process appeared.
    - "respawned": the PID is gone but a same-name process whose PID
      was not in known_pids is running.
    - "alive": the original PID is still there after the timeout.
    """
    import time as _time
    known = set(known_pids or [])
    end = _time.time() + timeout
    while _time.time() < end:
        # A zombie still has a /proc entry, so pid_exists() alone
        # lies: a killed-but-unreaped child looks "alive" forever.
        # A zombie IS dead — count it as gone.
        try:
            gone = (psutil.Process(pid).status()
                    == psutil.STATUS_ZOMBIE)
        except psutil.NoSuchProcess:
            gone = True
        except psutil.AccessDenied:
            gone = not psutil.pid_exists(pid)
        if gone:
            for p in psutil.process_iter(["pid", "name"]):
                try:
                    info = p.info
                    if (info["pid"] != pid and info["pid"] not in known
                            and (info.get("name") or "").lower()
                            == (name or "").lower()):
                        return "respawned", info["pid"]
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return "gone", None
        _time.sleep(0.2)
    return "alive", None


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
