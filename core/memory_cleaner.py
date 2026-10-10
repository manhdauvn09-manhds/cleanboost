"""Per-OS RAM freeing techniques (no process is killed)."""
import ctypes
from ctypes import wintypes
import os
import subprocess
import sys

import psutil


def trim_working_sets():
    """Windows: EmptyWorkingSet cho từng process truy cập được.

    Đẩy RAM nhàn rỗi của app ra standby/pagefile. Không cần admin
    cho process của chính mình; cần admin để trim process khác.
    """
    if sys.platform != "win32":
        return False, "Windows only."
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # Khai báo argtypes/restype: HANDLE là 64-bit trên Windows 64-bit,
    # không khai báo ctypes sẽ cắt handle còn 32-bit gây lỗi âm thầm.
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL,
                                     wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
    psapi.EmptyWorkingSet.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_SET_QUOTA = 0x0100
    done = 0
    for pid in psutil.pids():
        try:
            h = kernel32.OpenProcess(
                PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA, False, pid)
            if not h:
                continue
            try:
                if psapi.EmptyWorkingSet(h):
                    done += 1
            finally:
                kernel32.CloseHandle(h)
        except Exception:
            continue
    return True, f"Trimmed working set of {done} process(es)."


def purge_standby_list():
    """Windows: xả Standby List qua NtSetSystemInformation (cần Admin).

    Hiệu quả nhất khi chuẩn bị chạy game/app nặng: dọn cache RAM
    mà Windows đang giữ để nhường chỗ cho app mới.
    """
    if sys.platform != "win32":
        return False, "Windows only."
    try:
        ntdll = ctypes.WinDLL("ntdll")
        MEMORY_PURGE_STANDBY_LIST = 4
        cmd = ctypes.c_int(MEMORY_PURGE_STANDBY_LIST)
        status = ntdll.NtSetSystemInformation(80, ctypes.byref(cmd),
                                              ctypes.sizeof(cmd))
        if status == 0:
            return True, "Standby List flushed."
        return False, (
            "Could not flush Standby List (usually missing Admin rights). "
            f"Mã NTSTATUS: {status & 0xFFFFFFFF:#x}"
        )
    except Exception as e:  # noqa: BLE001
        return False, f"Error flushing Standby List: {e}"


def drop_caches():
    """Linux: xả page cache (cần root)."""
    if sys.platform == "win32":
        return False, "Linux only."
    if os.geteuid() != 0:
        return False, "Root required — run: sudo python3 main.py freeram"
    try:
        subprocess.run(["sync"], check=False)
        with open("/proc/sys/vm/drop_caches", "w") as f:
            f.write("3")
        return True, "Page cache dropped (drop_caches=3)."
    except Exception as e:  # noqa: BLE001
        return False, f"Error dropping caches: {e}"


def light_clean() -> list:
    """Light RAM clean: kills nothing. Returns a list of messages."""
    msgs = []
    if sys.platform == "win32":
        _, m1 = trim_working_sets()
        msgs.append(m1)
        _, m2 = purge_standby_list()
        msgs.append(m2)
    else:
        _, m = drop_caches()
        msgs.append(m)
    return msgs
