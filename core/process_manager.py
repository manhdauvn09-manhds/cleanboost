"""Liệt kê & kill process an toàn (luôn đi qua lớp bảo vệ)."""
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
    """Danh sách process, mặc định ẩn process hệ thống bị block."""
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
    """Kill 1 process. Trả về (ok, message). Không bao giờ hỏi user ở đây."""
    try:
        p = psutil.Process(pid)
        name = p.name() or f"PID {pid}"
    except psutil.NoSuchProcess:
        return False, "Tiến trình không còn tồn tại."
    except psutil.AccessDenied:
        return False, "⛔ Không đọc được thông tin process (cần quyền cao hơn)."

    if protected.check_process(name, pid) == "block":
        return False, (
            f"⛔ {name} (PID {pid}) là tiến trình hệ thống được BẢO VỆ — "
            "từ chối kill để tránh sập OS."
        )
    try:
        if force:
            p.kill()
        else:
            p.terminate()  # cho app cơ hội tự dọn dẹp
            try:
                p.wait(timeout=5)
            except psutil.TimeoutExpired:
                p.kill()  # lì quá -> force
        return True, f"✅ Đã {'force kill' if force else 'kill'} {name} (PID {pid})."
    except psutil.NoSuchProcess:
        return True, f"✅ {name} (PID {pid}) đã thoát."
    except psutil.AccessDenied:
        return False, (
            "⛔ Access denied — hãy chạy app với quyền Admin "
            "(Windows) / sudo (Linux) rồi thử lại."
        )


def emergency_candidates(min_rss_mb: int = 200) -> list:
    """Các process CỦA USER HIỆN TẠI, ngốn RAM, không bị bảo vệ.

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
