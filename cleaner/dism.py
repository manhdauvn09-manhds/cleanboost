"""Tích hợp DISM (Windows) — dọn WinSxS bằng công cụ chính chủ Microsoft.

Cần quyền Admin. Các lệnh có thể chạy vài phút -> timeout dài.
"""
import subprocess
import sys

from core import privilege


def _run(args: list, timeout: int = 1800):
    r = subprocess.run(["dism.exe"] + args, capture_output=True,
                       text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _check():
    if sys.platform != "win32":
        return False, "DISM chỉ có trên Windows."
    if not privilege.is_admin():
        return False, "Cần quyền Admin để chạy DISM."
    return True, ""


def component_cleanup():
    """DISM /Online /Cleanup-Image /StartComponentCleanup — an toàn."""
    ok, msg = _check()
    if not ok:
        return False, msg
    try:
        rc, out = _run(["/Online", "/Cleanup-Image", "/StartComponentCleanup"])
        if rc == 0:
            return True, "DISM StartComponentCleanup hoàn tất."
        tail = out.strip().splitlines()
        return False, f"DISM thất bại: {tail[-1][:160] if tail else rc}"
    except subprocess.TimeoutExpired:
        return False, "DISM chạy quá 30 phút — đã dừng chờ, có thể chạy lại."
    except Exception as e:  # noqa: BLE001
        return False, f"Lỗi DISM: {e}"


def reset_base():
    """DISM ... /StartComponentCleanup /ResetBase — 🔴 KHÔNG UNDO ĐƯỢC.

    Sau khi chạy: không gỡ được các update Windows đã cài.
    Chỉ gọi khi user đã tick riêng + xác nhận.
    """
    ok, msg = _check()
    if not ok:
        return False, msg
    try:
        rc, out = _run(["/Online", "/Cleanup-Image",
                        "/StartComponentCleanup", "/ResetBase"])
        if rc == 0:
            return True, "DISM ResetBase hoàn tất (không thể undo)."
        tail = out.strip().splitlines()
        return False, f"DISM ResetBase thất bại: {tail[-1][:160] if tail else rc}"
    except subprocess.TimeoutExpired:
        return False, "DISM ResetBase quá 30 phút — đã dừng chờ."
    except Exception as e:  # noqa: BLE001
        return False, f"Lỗi DISM ResetBase: {e}"
