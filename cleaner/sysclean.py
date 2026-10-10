"""Các thao tác dọn hệ thống theo OS (dùng bởi special rules).

Mỗi hàm trả về (ok, message[, bytes]) và KHÔNG BAO GIỜ raise.
Các hàm nguy hiểm (high risk) chỉ được gọi khi user tick riêng + xác nhận.
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
        return False, "Chỉ hỗ trợ Windows."
    if not privilege.is_admin():
        return False, "Cần quyền Admin."
    rc, out = _run(["powercfg", "/hibernate", "off"], timeout=60)
    if rc == 0 and not os.path.exists(
            os.path.join(os.environ.get("SystemDrive", "C:"), "hiberfil.sys")):
        return True, "Đã tắt Hibernate, xóa hiberfil.sys."
    if rc == 0:
        return True, "Đã chạy powercfg /hibernate off."
    return False, f"Không tắt được Hibernate: {out.strip()[:160]}"


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


def prune_old_restore_points():
    """🔴 Xóa các restore point cũ, GIỮ LẠI điểm mới nhất.

    Dùng vssadmin: liệt kê shadow copies, xóa tất cả trừ mới nhất.
    """
    if sys.platform != "win32":
        return False, "Chỉ hỗ trợ Windows.", 0
    if not privilege.is_admin():
        return False, "Cần quyền Admin.", 0
    rc, out = _run(["vssadmin", "list", "shadows"], timeout=120)
    if rc != 0:
        return False, "Không đọc được danh sách shadow copies.", 0
    # mỗi block "Shadow Copy ID: {xxx}" kèm "Original Volume: (C:)\\?\Volume{...}\"
    ids = re.findall(r"Shadow Copy ID:\s*(\{[0-9a-fA-F-]+\})", out)
    if len(ids) <= 1:
        return True, "Chỉ có 0-1 restore point — không cần xóa.", 0
    # vssadmin liệt kê theo thời gian tăng dần -> giữ cái cuối
    removed = 0
    for sid in ids[:-1]:
        rc2, _ = _run(["vssadmin", "delete", "shadows",
                       f"/shadow={sid}", "/quiet"], timeout=120)
        if rc2 == 0:
            removed += 1
    return True, (f"Đã xóa {removed}/{len(ids) - 1} restore point cũ, "
                  "giữ lại điểm mới nhất."), 0


def empty_update_cache():
    """Dọn C:\\Windows\\SoftwareDistribution\\Download: dừng wuauserv,
    xóa file, start lại service."""
    if sys.platform != "win32":
        return False, "Chỉ hỗ trợ Windows.", 0
    if not privilege.is_admin():
        return False, "Cần quyền Admin.", 0
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
    return True, f"Đã dọn Windows Update cache ({n} file).", freed


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
        return False, "Chỉ hỗ trợ Linux.", 0
    if os.geteuid() != 0:
        return False, "Cần root (chạy bằng sudo).", 0
    before = apt_cache_size()
    rc, _ = _run(["apt-get", "clean", "-y"], timeout=300)
    if rc == 0:
        return True, "Đã chạy apt-get clean.", before - apt_cache_size()
    return False, "apt-get clean thất bại.", 0


def snap_prune_old():
    """Gỡ các bản snap 'disabled' (cũ)."""
    if shutil.which("snap") is None:
        return False, "Không tìm thấy snap.", 0
    if os.geteuid() != 0:
        return False, "Cần root (chạy bằng sudo).", 0
    rc, out = _run(["snap", "list", "--all"], timeout=60)
    if rc != 0:
        return False, "Không đọc được snap list.", 0
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
    return True, f"Đã gỡ {removed} bản snap cũ.", 0


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
        return False, "Cần root (chạy bằng sudo).", 0
    targets = old_kernels_info()
    if not targets:
        return True, "Không có kernel cũ nào để gỡ.", 0
    rc, out = _run(["apt-get", "purge", "-y"] + targets, timeout=900)
    if rc == 0:
        _run(["update-grub"], timeout=120)
        return True, f"Đã gỡ {len(targets)} kernel cũ.", 0
    return False, f"Gỡ kernel thất bại: {out.strip()[-160:]}", 0


# ------------------------- Chung -------------------------

def docker_prune():
    """Xóa image/container/network Docker không dùng (không xóa volume)."""
    if shutil.which("docker") is None:
        return False, "Không tìm thấy docker.", 0
    rc, out = _run(["docker", "system", "prune", "-f"], timeout=600)
    if rc == 0:
        m = re.search(r"Total reclaimed space:\s*([\d.]+\s*\w+)", out)
        return True, "Đã prune Docker" + (f" ({m.group(1)})." if m else "."), 0
    return False, f"docker prune thất bại: {out.strip()[-160:]}", 0
