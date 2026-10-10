"""DISM integration (Windows) — clean WinSxS with Microsoft's own tool.

Needs Admin rights. Commands may run for minutes -> long timeout.
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
        return False, "DISM is Windows-only."
    if not privilege.is_admin():
        return False, "Admin rights are required to run DISM."
    return True, ""


def component_cleanup():
    """DISM /Online /Cleanup-Image /StartComponentCleanup — safe."""
    ok, msg = _check()
    if not ok:
        return False, msg
    try:
        rc, out = _run(["/Online", "/Cleanup-Image", "/StartComponentCleanup"])
        if rc == 0:
            return True, "DISM StartComponentCleanup finished."
        tail = out.strip().splitlines()
        return False, f"DISM failed: {tail[-1][:160] if tail else rc}"
    except subprocess.TimeoutExpired:
        return False, "DISM ran over 30 minutes — stopped waiting, you can retry."
    except Exception as e:  # noqa: BLE001
        return False, f"DISM error: {e}"


def reset_base():
    """DISM ... /StartComponentCleanup /ResetBase — CANNOT BE UNDONE.

    After running: installed Windows updates cannot be removed.
    Only call when the user ticked it explicitly + confirmed.
    """
    ok, msg = _check()
    if not ok:
        return False, msg
    try:
        rc, out = _run(["/Online", "/Cleanup-Image",
                        "/StartComponentCleanup", "/ResetBase"])
        if rc == 0:
            return True, "DISM ResetBase finished (cannot be undone)."
        tail = out.strip().splitlines()
        return False, f"DISM ResetBase failed: {tail[-1][:160] if tail else rc}"
    except subprocess.TimeoutExpired:
        return False, "DISM ResetBase ran over 30 minutes — stopped waiting."
    except Exception as e:  # noqa: BLE001
        return False, f"DISM ResetBase error: {e}"
