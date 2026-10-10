"""Create a System Restore Point (Windows) before cleaning levels 2/3."""
import subprocess
import sys

from core import privilege


def create(description: str = "CleanBoost - truoc khi don rac"):
    """Returns (ok, message). Never raises."""
    if sys.platform != "win32":
        return False, ("Linux: the app does not create restore points — "
                       "use Timeshift manually if needed.")
    if not privilege.is_admin():
        return False, "Admin rights are required to create a System Restore Point."
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"Checkpoint-Computer -Description '{description}' "
             "-RestorePointType 'MODIFY_SETTINGS'"],
            capture_output=True, text=True, timeout=180)
        if r.returncode == 0:
            return True, "System Restore Point created."
        err = (r.stderr or "").strip().splitlines()
        return False, f"Could not create restore point: {err[0][:180] if err else 'unknown'}"
    except Exception as e:  # noqa: BLE001
        return False, f"Error creating restore point: {e}"
