"""Tạo System Restore Point (Windows) trước khi dọn mức 2/3."""
import subprocess
import sys

from core import privilege


def create(description: str = "CleanBoost - truoc khi don rac"):
    """Trả về (ok, message). Không bao giờ raise."""
    if sys.platform != "win32":
        return False, ("Linux: app không tự tạo restore point — "
                       "bạn nên dùng Timeshift thủ công nếu cần.")
    if not privilege.is_admin():
        return False, "Cần quyền Admin để tạo System Restore Point."
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"Checkpoint-Computer -Description '{description}' "
             "-RestorePointType 'MODIFY_SETTINGS'"],
            capture_output=True, text=True, timeout=180)
        if r.returncode == 0:
            return True, "Đã tạo System Restore Point."
        err = (r.stderr or "").strip().splitlines()
        return False, f"Không tạo được restore point: {err[0][:180] if err else 'unknown'}"
    except Exception as e:  # noqa: BLE001
        return False, f"Lỗi khi tạo restore point: {e}"
