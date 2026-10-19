"""Lớp bảo vệ: process & đường dẫn KHÔNG BAO GIỜ được kill/xóa.

- "block": chặn cứng (kill = sập OS / mất dữ liệu).
- "warn": cho kill nhưng phải hỏi lại user (vd: explorer.exe -> mất taskbar vài giây).
- "ok": an toàn.
"""
import os
import sys

# Kill các process này gần như chắc chắn gây màn hình xanh / sập Windows
_HARD_BLOCK_WIN = {
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "lsaiso.exe", "winlogon.exe",
    "fontdrvhost.exe", "spoolsv.exe",
    # v2.5.2: svchost hosts Windows services — killing one kills every
    # service in it and can destabilize the OS. TrustedInstaller owns
    # Windows Update / component store — killing it can corrupt updates.
    "svchost.exe", "trustedinstaller.exe",
}
# Kill được nhưng gây khó chịu -> bắt user xác nhận
_WARN_WIN = {
    "dwm.exe", "explorer.exe", "taskhostw.exe", "sihost.exe",
    "ctfmon.exe", "searchindexer.exe",
}

# Đường dẫn cấm tuyệt đối trên Windows (chỉ tool chính chủ như DISM được động vào)
_PROTECTED_PREFIX_WIN = [
    r"C:\Windows\System32",
    r"C:\Windows\SysWOW64",
    r"C:\Windows\Sysnative",
    r"C:\Windows\WinSxS",
    r"C:\Windows\Installer",  # chứa .msi gốc -> xóa nhầm là khỏi gỡ app
]

_PROTECTED_PREFIX_LINUX = [
    "/bin", "/sbin", "/lib", "/lib64",
    "/usr/bin", "/usr/sbin", "/usr/lib",
    "/etc", "/boot", "/dev", "/proc", "/sys", "/root",
]


# --- Sensitive network ports (CleanBoost v2.4, Port Inspector) ---
# Ports that are risky when bound to 0.0.0.0 (open to the whole LAN).
# Used by network/ports.py via port_severity(). Never blocks anything
# by itself — it only labels rows in the UI.
SENSITIVE_PORTS = {
    21: "FTP",
    23: "Telnet",
    445: "SMB",
    3306: "MySQL",
    3389: "Remote Desktop",
    5432: "PostgreSQL",
    5900: "VNC",
}


def port_severity(port: int, bind_ip: str) -> str:
    """Severity of a LISTEN port: 'critical' | 'warning' | 'normal'.

    critical: sensitive port open to the whole network (0.0.0.0 / ::).
    warning:  sensitive port, but bound to localhost only.
    normal:   everything else.
    """
    try:
        p = int(port)
    except (TypeError, ValueError):
        return "normal"
    if p not in SENSITIVE_PORTS:
        return "normal"
    if (bind_ip or "") in ("0.0.0.0", "::", ""):
        return "critical"
    if (bind_ip or "") in ("127.0.0.1", "::1"):
        return "warning"
    return "critical"


def _norm(p: str) -> str:
    return os.path.normcase(os.path.normpath(p))


def _user_data_dirs():
    """Thư mục dữ liệu cá nhân: không bao giờ tự động dọn."""
    if sys.platform == "win32":
        base = os.environ.get("USERPROFILE", "")
        names = ("Documents", "Desktop", "Downloads", "Pictures", "Videos")
    else:
        base = os.path.expanduser("~")
        names = ("Documents", "Desktop", "Downloads", "Pictures", "Videos")
    return [os.path.join(base, n) for n in names if base]


def check_process(name: str, pid: int) -> str:
    """Trả về 'block' | 'warn' | 'ok'."""
    n = (name or "").lower().strip()
    if sys.platform == "win32":
        if n in _HARD_BLOCK_WIN:
            return "block"
        if n in _WARN_WIN:
            return "warn"
        return "ok"
    # Linux
    if pid in (0, 1, 2):
        return "block"
    if n.startswith("[") and n.endswith("]"):
        return "block"  # kernel thread
    if n in {"systemd", "init"}:
        return "warn"
    return "ok"


def is_protected_path(path: str) -> bool:
    """True nếu path nằm trong vùng cấm.

    Dùng realpath để chống bypass qua symlink.
    """
    try:
        target = _norm(os.path.realpath(os.path.abspath(path)))
    except Exception:
        return True  # không chắc -> coi như cấm cho an toàn
    if sys.platform == "win32":
        prefixes = _PROTECTED_PREFIX_WIN
    else:
        prefixes = _PROTECTED_PREFIX_LINUX
    all_prefixes = prefixes + _user_data_dirs()
    for pre in all_prefixes:
        np = _norm(pre)
        if target == np or target.startswith(np + os.sep):
            return True
    return False
