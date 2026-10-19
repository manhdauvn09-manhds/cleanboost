"""OS-specific system cleanup operations (used by special rules).

Each function returns (ok, message[, bytes]) and NEVER raises.
Dangerous (high risk) functions only run when the user ticked them + confirmed.
"""
import os
import re
import shutil
import subprocess
import sys

from core import privilege


def _run(cmd: list, timeout: int = 300):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


# ------------------------- Windows -------------------------

def hiberfil_size() -> int:
    """Dung lượng hiberfil.sys nếu Hibernate đang bật."""
    if sys.platform != "win32":
        return 0
    p = os.path.join(os.environ.get("SystemDrive", "C:"), "hiberfil.sys")
    try:
        return os.path.getsize(p)
    except OSError:
        return 0


def hibernate_off():
    """🔴 Tắt Hibernate -> xóa hiberfil.sys (mất Hibernate + Fast Startup)."""
    if sys.platform != "win32":
        return False, "Windows only."
    if not privilege.is_admin():
        return False, "Admin rights required."
    rc, out = _run(["powercfg", "/hibernate", "off"], timeout=60)
    if rc == 0 and not os.path.exists(
            os.path.join(os.environ.get("SystemDrive", "C:"), "hiberfil.sys")):
        return True, "Hibernate disabled, hiberfil.sys removed."
    if rc == 0:
        return True, "Ran powercfg /hibernate off."
    return False, f"Could not disable Hibernate: {out.strip()[:160]}"


def count_restore_points() -> int:
    """Đếm số restore point (Windows)."""
    if sys.platform != "win32":
        return 0
    rc, out = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                    "Get-ComputerRestorePoint | Measure-Object | "
                    "Select-Object -ExpandProperty Count"], timeout=60)
    try:
        return int(out.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return 0


def _parse_vss_time(text):
    """Parse vssadmin 'Creation Time'. None when unparseable (keep it)."""
    from datetime import datetime
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S",
                "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    return None


def prune_old_restore_points():
    """🔴 Xóa các restore point cũ, GIỮ LẠI điểm mới nhất.

    SECURITY (v2.5.2): the newest is picked by parsed Creation Time
    (not list order), only shadow copies on the SystemDrive are
    touched (other volumes' backups are left alone), and anything
    whose date cannot be parsed is KEPT — never delete what we
    cannot positively identify as old.
    """
    if sys.platform != "win32":
        return False, "Windows only.", 0
    if not privilege.is_admin():
        return False, "Admin rights required.", 0
    rc, out = _run(["vssadmin", "list", "shadows"], timeout=120)
    if rc != 0:
        return False, "Could not read shadow copy list.", 0
    system_drive = os.environ.get("SystemDrive", "C:").rstrip("\\").upper()
    entries = []
    for block in re.split(r"\n\s*\n", out):
        m_id = re.search(r"Shadow Copy ID:\s*(\{[0-9a-fA-F-]+\})", block)
        if not m_id:
            continue
        m_vol = re.search(r"Original Volume:\s*\(([A-Za-z]):\)", block)
        m_time = re.search(r"Creation Time:\s*(.+)", block)
        vol = (m_vol.group(1).upper() + ":") if m_vol else ""
        ts = _parse_vss_time(m_time.group(1)) if m_time else None
        entries.append({"id": m_id.group(1), "vol": vol, "ts": ts})
    mine = [e for e in entries if e["vol"] == system_drive and e["ts"] is not None]
    if len(mine) <= 1:
        return True, ("Only 0-1 dated restore point(s) on the system drive "
                      "— nothing to remove."), 0
    newest = max(mine, key=lambda e: e["ts"])
    removed = 0
    for e in mine:
        if e["id"] == newest["id"]:
            continue
        rc2, _ = _run(["vssadmin", "delete", "shadows",
                       f"/shadow={e['id']}", "/quiet"], timeout=120)
        if rc2 == 0:
            removed += 1
    return True, (f"Deleted {removed}/{len(mine) - 1} old restore point(s), "
                  "kept the newest."), 0


def empty_update_cache():
    """Dọn C:\\Windows\\SoftwareDistribution\\Download: dừng wuauserv,
    xóa file, start lại service."""
    if sys.platform != "win32":
        return False, "Windows only.", 0
    if not privilege.is_admin():
        return False, "Admin rights required.", 0
    dl = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                      "SoftwareDistribution", "Download")
    _run(["net", "stop", "wuauserv"], timeout=60)
    freed, n = 0, 0
    try:
        for root, _d, files in os.walk(dl, onerror=lambda e: None):
            for fn in files:
                fp = os.path.join(root, fn)
                try:
                    freed += os.path.getsize(fp)
                    os.remove(fp)
                    n += 1
                except OSError:
                    continue
    finally:
        _run(["net", "start", "wuauserv"], timeout=60)
    return True, f"Windows Update cache cleaned ({n} file(s)).", freed


# ------------------------- Linux -------------------------

def apt_cache_size() -> int:
    total = 0
    for p in ("/var/cache/apt/archives",):
        if os.path.isdir(p):
            for root, _d, files in os.walk(p, onerror=lambda e: None):
                for fn in files:
                    try:
                        total += os.path.getsize(os.path.join(root, fn))
                    except OSError:
                        continue
    return total


def apt_clean():
    if sys.platform == "win32":
        return False, "Linux only.", 0
    if os.geteuid() != 0:
        return False, "Root required (run with sudo).", 0
    before = apt_cache_size()
    rc, _ = _run(["apt-get", "clean", "-y"], timeout=300)
    if rc == 0:
        return True, "Ran apt-get clean.", before - apt_cache_size()
    return False, "apt-get clean failed.", 0


def snap_prune_old():
    """Gỡ các bản snap 'disabled' (cũ)."""
    if shutil.which("snap") is None:
        return False, "snap not found.", 0
    if os.geteuid() != 0:
        return False, "Root required (run with sudo).", 0
    rc, out = _run(["snap", "list", "--all"], timeout=60)
    if rc != 0:
        return False, "Could not read snap list.", 0
    removed = 0
    for line in out.splitlines()[1:]:
        parts = line.split()
        # Name  Version  Rev  Tracking  Publisher  Notes
        if len(parts) >= 6 and "disabled" in parts[5]:
            name, rev = parts[0], parts[2]
            rc2, _ = _run(["snap", "remove", name, "--revision", rev],
                          timeout=300)
            if rc2 == 0:
                removed += 1
    return True, f"Removed {removed} old snap revision(s).", 0


def old_kernels_info():
    """Liệt kê kernel có thể gỡ (giữ kernel đang chạy + 2 bản mới nhất)."""
    if shutil.which("dpkg") is None:
        return []
    rc, out = _run(["dpkg", "--list"], timeout=60)
    if rc != 0:
        return []
    running = os.uname().release
    kernels = []
    for line in out.splitlines():
        m = re.match(r"^ii\s+(linux-image-(\d[\w.-]*))\s", line)
        if m and m.group(2) not in running and "generic" in m.group(1):
            kernels.append(m.group(1))
    kernels.sort()
    # giữ 2 bản mới nhất (sort theo tên ~ sort theo version với generic)
    return kernels[:-2] if len(kernels) > 2 else []


def purge_old_kernels():
    """🔴 Gỡ kernel cũ (giữ kernel đang chạy + 2 bản mới nhất)."""
    if os.geteuid() != 0:
        return False, "Root required (run with sudo).", 0
    targets = old_kernels_info()
    if not targets:
        return True, "No old kernels to remove.", 0
    rc, out = _run(["apt-get", "purge", "-y"] + targets, timeout=900)
    if rc == 0:
        _run(["update-grub"], timeout=120)
        return True, f"Removed {len(targets)} old kernel(s).", 0
    return False, f"Kernel removal failed: {out.strip()[-160:]}", 0


# ------------------------- Chung -------------------------

def docker_prune():
    """Xóa image/container/network Docker không dùng (không xóa volume)."""
    if shutil.which("docker") is None:
        return False, "docker not found.", 0
    rc, out = _run(["docker", "system", "prune", "-f"], timeout=600)
    if rc == 0:
        m = re.search(r"Total reclaimed space:\s*([\d.]+\s*\w+)", out)
        return True, "Docker pruned" + (f" ({m.group(1)})." if m else "."), 0
    return False, f"docker prune failed: {out.strip()[-160:]}", 0
