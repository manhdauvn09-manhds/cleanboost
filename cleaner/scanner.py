"""Dry-run scan: only COUNTS size, deletes NOTHING.

Level 1 dry-run scan. Real cleanup + quarantine are handled by clean.py.
"""
import ctypes
import fnmatch
import os
import re
import subprocess
import sys
import time

from cleaner import engine
from cleaner.fs_walk import safe_walk
from safety import protected


MAX_PATHS = 200_000  # cap to avoid RAM blowup on whole-drive scans


def _match(name: str, patterns: list, exclude: list) -> bool:
    if exclude and any(fnmatch.fnmatch(name, e) for e in exclude):
        return False
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def _old_enough(path: str, min_age_days: int) -> bool:
    if not min_age_days:
        return True
    try:
        return (time.time() - os.path.getmtime(path)) >= min_age_days * 86400
    except OSError:
        return False


def scan_rule(rule: dict, collect_paths: bool = False) -> dict:
    """Returns {rule, size, count, samples[], paths?[], error?}.

    collect_paths=True: also returns the full file list (used for real cleanup).
    """
    if rule.get("special"):
        return _scan_special(rule)
    size, count, samples = 0, 0, []
    paths = [] if collect_paths else None
    patterns = rule.get("patterns", ["*"])
    exclude = rule.get("exclude", [])
    min_age = rule.get("min_age_days", 0)
    truncated = False

    def consider(fp: str) -> bool:
        """Process one file. Returns False when the path cap is hit."""
        nonlocal size, count, truncated
        try:
            if not _match(os.path.basename(fp), patterns, exclude):
                return True
            if not _old_enough(fp, min_age):
                return True
            size += os.path.getsize(fp)
            count += 1
            if len(samples) < 5:
                samples.append(fp)
            if paths is not None:
                if len(paths) >= MAX_PATHS:
                    truncated = True
                    return False
                paths.append(fp)
            return True
        except OSError:
            return True  # locked / vanished mid-scan -> skip

    for base in engine.resolve_paths(rule):
        if truncated:
            break
        if protected.is_protected_path(base):
            continue
        if os.path.isfile(base):
            consider(base)
        else:
            # v2.6.1: safe_walk never descends into junctions (Windows
            # "Application Data" loops) and caps depth.
            for root, _dirs, filenames in safe_walk(base):
                if protected.is_protected_path(root):
                    continue
                for fn in filenames:
                    if not consider(os.path.join(root, fn)):
                        break
                else:
                    continue
                break
    out = {"rule": rule, "size": size, "count": count, "samples": samples}
    if paths is not None:
        out["paths"] = paths
    if truncated:
        out["truncated"] = True
    return out


def _dir_size(path: str):
    total, count = 0, 0
    for root, _d, files in safe_walk(path):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(root, fn))
                count += 1
            except OSError:
                continue
    return total, count


def _scan_special(rule: dict) -> dict:
    kind = rule["special"]
    if kind in ("update_cache", "dism_cleanup", "dism_resetbase",
                "orphan_apps", "hibernate_off", "old_restore_points",
                "docker_prune", "apt_clean", "snap_old", "old_kernels"):
        return _scan_special2(rule)
    if kind == "recycle_bin" and sys.platform == "win32":
        try:
            class _INFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_ulong),
                            ("i64Size", ctypes.c_longlong),
                            ("i64NumItems", ctypes.c_longlong)]
            info = _INFO()
            info.cbSize = ctypes.sizeof(_INFO)
            ok = ctypes.WinDLL("shell32").SHQueryRecycleBinW(None,
                                                             ctypes.byref(info))
            if ok == 0:
                return {"rule": rule, "size": info.i64Size,
                        "count": info.i64NumItems, "samples": []}
        except Exception:  # noqa: BLE001
            pass
        return {"rule": rule, "size": 0, "count": 0, "samples": [],
                "error": "Could not read Recycle Bin"}
    if kind == "trash":
        p = os.path.expanduser("~/.local/share/Trash/files")
        if os.path.isdir(p):
            s, c = _dir_size(p)
            return {"rule": rule, "size": s, "count": c, "samples": []}
        return {"rule": rule, "size": 0, "count": 0, "samples": []}
    if kind == "journal":
        try:
            r = subprocess.run(["journalctl", "--disk-usage"],
                               capture_output=True, text=True, timeout=10)
            m = re.search(r"take up ([\d.]+)([KMG])", r.stdout)
            if m:
                mult = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}[m.group(2)]
                return {"rule": rule,
                        "size": int(float(m.group(1)) * mult),
                        "count": 0, "samples": [],
                        "note": "On real clean: journalctl --vacuum-time=7d"}
        except Exception:  # noqa: BLE001
            pass
        return {"rule": rule, "size": 0, "count": 0, "samples": []}
    return {"rule": rule, "size": 0, "count": 0, "samples": [],
            "error": f"special '{kind}' not supported"}


def _scan_special2(rule: dict) -> dict:
    """Special rules (levels 2/3)."""
    from cleaner import sysclean, orphan_detector
    kind = rule["special"]
    if kind == "update_cache":
        dl = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                          "SoftwareDistribution", "Download")
        s, c = _dir_size(dl) if os.path.isdir(dl) else (0, 0)
        return {"rule": rule, "size": s, "count": c, "samples": []}
    if kind == "dism_cleanup":
        return {"rule": rule, "size": 0, "count": 0, "samples": [],
                "note": "Runs DISM StartComponentCleanup (takes a few minutes)"}
    if kind == "dism_resetbase":
        return {"rule": rule, "size": 0, "count": 0, "samples": [],
                "note": "DISM /ResetBase — CANNOT be undone"}
    if kind == "orphan_apps":
        orphans = orphan_detector.detect_orphans()
        total = sum(o["size"] for o in orphans)
        hi = sum(1 for o in orphans if o["confidence"] == "high")
        samples = [f"[{o['confidence']}] {o['path']}" for o in orphans[:5]]
        return {"rule": rule, "size": total, "count": len(orphans),
                "samples": samples, "orphans": orphans,
                "note": f"{len(orphans)} suspected orphan folders ({hi} high confidence)"}
    if kind == "hibernate_off":
        s = sysclean.hiberfil_size()
        return {"rule": rule, "size": s, "count": 1 if s else 0,
                "samples": [],
                "note": "hiberfil.sys not found (Hibernate is off)" if not s else ""}
    if kind == "old_restore_points":
        n = sysclean.count_restore_points()
        return {"rule": rule, "size": 0, "count": n, "samples": [],
                "note": f"{n} restore point(s) found (newest will be kept)"}
    if kind == "docker_prune":
        return {"rule": rule, "size": 0, "count": 0, "samples": [],
                "note": "docker system prune (volumes kept)"}
    if kind == "apt_clean":
        return {"rule": rule, "size": sysclean.apt_cache_size(),
                "count": 0, "samples": []}
    if kind == "snap_old":
        return {"rule": rule, "size": 0, "count": 0, "samples": [],
                "note": "Removes disabled snap revisions"}
    if kind == "old_kernels":
        ks = sysclean.old_kernels_info()
        return {"rule": rule, "size": 0, "count": len(ks), "samples": ks,
                "note": "Keeps the running kernel + 2 newest"}
    return {"rule": rule, "size": 0, "count": 0, "samples": [],
            "error": f"special '{kind}' not supported"}


def scan_all(level: int) -> list:
    return [scan_rule(r) for r in engine.rules_for(level)]
