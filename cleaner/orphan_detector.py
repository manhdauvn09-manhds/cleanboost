"""Phát hiện dữ liệu mồ côi của app đã gỡ (orphan detector).

Windows: đọc registry Uninstall -> tập app đang cài (token hóa tên),
so với thư mục trong %APPDATA% / %LOCALAPPDATA% / %ProgramData%.
Linux: so ~/.local/share + ~/.config với các .desktop đã cài.

Thư mục nào KHÔNG khớp app đang cài + không được đụng tới > 90 ngày
+ không có process đang chạy trỏ tới -> gắn cờ "mồ côi".

Kết quả chỉ là GỢI Ý có độ tin cậy (high/medium) — luôn đi qua
khu cách ly, và rule tương ứng mặc định KHÔNG tick.
"""
import os
import re
import sys
import time

import psutil

from safety import protected

# Thư mục hệ thống trong AppData: không bao giờ coi là mồ côi
_SKIP_DIRS_WIN = {"microsoft", "windows", "packages"}
_SKIP_DIRS_LINUX = {"applications", "fonts", "icons", "mime", "themes",
                    "man", "doc", "metainfo", "appdata"}

_STOPWORDS = {"inc", "corp", "corporation", "ltd", "llc", "co", "the", "for",
              "windows", "microsoft", "app", "apps", "software", "x64", "x86",
              "bit", "with", "and", "client", "desktop"}


def _tokens(s: str) -> set:
    s = (s or "").lower()
    s = re.sub(r"\d+(\.\d+)*", " ", s)  # bỏ số version
    parts = re.split(r"[^a-z0-9]+", s)
    return {p for p in parts if len(p) > 2 and p not in _STOPWORDS}


def _win_installed_tokens() -> set:
    import winreg
    names = []
    hives = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, path in hives:
        try:
            with winreg.OpenKey(hive, path) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        with winreg.OpenKey(key, winreg.EnumKey(key, i)) as sub:
                            name, _ = winreg.QueryValueEx(sub, "DisplayName")
                    except OSError:
                        continue
                    if name:
                        names.append(str(name))
        except OSError:
            continue
    toks = set()
    for n in names:
        toks |= _tokens(n)
    return toks


def _linux_installed_tokens() -> set:
    toks = set()
    for d in ("/usr/share/applications",
              os.path.expanduser("~/.local/share/applications")):
        if not os.path.isdir(d):
            continue
        try:
            for fn in os.listdir(d):
                if not fn.endswith(".desktop"):
                    continue
                try:
                    with open(os.path.join(d, fn), encoding="utf-8",
                              errors="ignore") as f:
                        for line in f:
                            if line.startswith("Name="):
                                toks |= _tokens(line[5:])
                                break
                except OSError:
                    continue
        except OSError:
            continue
    # cộng thêm tên package hệ thống nếu có dpkg (best-effort)
    return toks


def _running_names() -> set:
    names = set()
    try:
        for p in psutil.process_iter(["name"]):
            n = (p.info.get("name") or "").lower()
            if n:
                names.add(os.path.splitext(n)[0])
    except Exception:  # noqa: BLE001
        pass
    return names


def _dir_size(path: str, cap_files: int = 200000) -> int:
    total, n = 0, 0
    for root, _d, files in os.walk(path, onerror=lambda e: None):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except OSError:
                continue
            n += 1
            if n > cap_files:
                return total
    return total


def _older_than(path: str, days: int) -> bool:
    try:
        return (time.time() - os.path.getatime(path)) >= days * 86400
    except OSError:
        return False


def _own_data_dirs() -> list:
    """Thư mục dữ liệu của chính CleanBoost: không bao giờ gắn cờ mồ côi."""
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        local = os.path.expandvars("%LOCALAPPDATA%")
        prog = os.path.expandvars("%PROGRAMDATA%")
        return [os.path.join(local, "CleanBoost"),
                os.path.join(prog, "CleanBoost")]
    return [os.path.join(home, ".local", "share", "cleanboost"),
            os.path.join(home, ".config", "cleanboost")]


def _scan_bases(bases: list, installed: set, skip: set,
                min_age_days: int) -> list:
    running = _running_names()
    own = [os.path.normcase(os.path.abspath(p)) for p in _own_data_dirs()]
    out = []
    for base in bases:
        if not os.path.isdir(base):
            continue
        try:
            entries = list(os.scandir(base))
        except OSError:
            continue
        for entry in entries:
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
                path = entry.path
                name = entry.name
            except OSError:
                continue
            if protected.is_protected_path(path):
                continue
            np = os.path.normcase(os.path.abspath(path))
            if any(np == o or np.startswith(o + os.sep) for o in own):
                continue  # dữ liệu của chính CleanBoost
            lname = name.lower()
            if lname in skip or name.startswith("."):
                continue
            ftoks = _tokens(name)
            if ftoks & installed:
                continue  # khớp app đang cài
            # kiểm tra chéo: còn process đang chạy trỏ tới? (substring, token dài)
            if any(len(ft) > 4 and ft in r
                   for r in running for ft in ftoks):
                continue
            old = _older_than(path, min_age_days)
            size = _dir_size(path)
            if size == 0:
                continue
            confidence = "high" if old else "medium"
            reason = ("không khớp app đang cài"
                      + (" + không dùng > %d ngày" % min_age_days if old
                         else " (mới dùng gần đây — cần xem lại)"))
            out.append({"path": path, "size": size,
                        "confidence": confidence, "reason": reason})
    out.sort(key=lambda x: x["size"], reverse=True)
    return out


def detect_orphans(min_age_days: int = 90) -> list:
    """Trả về list {path, size, confidence, reason}, sắp xếp theo size."""
    if sys.platform == "win32":
        installed = _win_installed_tokens()
        bases = [os.path.expandvars(p) for p in
                 ("%APPDATA%", "%LOCALAPPDATA%", "%PROGRAMDATA%")]
        return _scan_bases(bases, installed, _SKIP_DIRS_WIN, min_age_days)
    installed = _linux_installed_tokens()
    home = os.path.expanduser("~")
    bases = [os.path.join(home, ".local", "share"),
             os.path.join(home, ".config")]
    return _scan_bases(bases, installed, _SKIP_DIRS_LINUX, min_age_days)
