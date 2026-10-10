"""Engine dọn THẬT.

Luồng: pre-flight (restore point nếu level>=2 trên Windows)
  -> với từng rule được chọn: duyệt lại full file list
  -> kiểm tra protected path lần cuối
  -> mặc định CHUYỂN vào khu cách ly; chỉ xóa vĩnh viễn khi user chọn.
Không bao giờ raise — mọi lỗi gom vào summary["failed"].
"""
import ctypes
import os
import shutil
import subprocess
import sys

from cleaner import scanner
from cleaner import quarantine as Q
from cleaner import restore_point, action_log
from core import privilege
from safety import protected


def _clean_special(rule: dict, res: dict = None, permanent: bool = False):
    """Xử lý các rule đặc biệt.

    Trả về (ok, message, freed_bytes, stats) với
    stats = {"quarantined": int, "deleted": int}.
    """
    kind = rule["special"]
    if kind in ("update_cache", "dism_cleanup", "dism_resetbase",
                "orphan_apps", "hibernate_off", "old_restore_points",
                "docker_prune", "apt_clean", "snap_old", "old_kernels"):
        return _clean_special2(rule, res, permanent)
    if kind == "recycle_bin" and sys.platform == "win32":
        try:
            SHERB = 0x1 | 0x2 | 0x4  # NOCONFIRMATION | NOPROGRESSUI | NOSOUND
            rc = ctypes.WinDLL("shell32").SHEmptyRecycleBinW(None, None, SHERB)
            if rc == 0:
                return True, "Đã dọn sạch Recycle Bin.", 0, {"deleted": 0}
            return False, "Không dọn được Recycle Bin.", 0, {}
        except Exception as e:  # noqa: BLE001
            return False, f"Lỗi Recycle Bin: {e}", 0, {}
    if kind == "trash":
        freed, n = 0, 0
        for sub in ("files", "info"):
            p = os.path.expanduser(f"~/.local/share/Trash/{sub}")
            if not os.path.isdir(p):
                continue
            for root, dirs, files in os.walk(p):
                for fn in files:
                    fp = os.path.join(root, fn)
                    try:
                        freed += os.path.getsize(fp)
                        os.remove(fp)
                        n += 1
                    except OSError:
                        continue
        return True, f"Đã dọn thùng rác ({n} file).", freed, {"deleted": n}
    if kind == "journal":
        if os.geteuid() != 0:
            return False, "Cần root để vacuum journal (chạy bằng sudo).", 0, {}
        try:
            r = subprocess.run(["journalctl", "--vacuum-time=7d"],
                               capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                return True, "Đã vacuum journal (giữ 7 ngày).", 0, {"deleted": 0}
            return False, "journalctl thất bại.", 0, {}
        except Exception as e:  # noqa: BLE001
            return False, f"Lỗi journal: {e}", 0, {}
    return False, f"special '{kind}' chưa hỗ trợ dọn thật.", 0, {}


def _clean_special2(rule: dict, res: dict = None, permanent: bool = False):
    """Các special của Phase 3 (mức 2/3).

    Trả về (ok, message, freed_bytes, stats).
    """
    from cleaner import sysclean, dism, orphan_detector
    kind = rule["special"]
    if kind == "update_cache":
        ok, msg, freed = sysclean.empty_update_cache()
        return ok, msg, freed, {"deleted": 0}
    if kind == "dism_cleanup":
        ok, msg = dism.component_cleanup()
        return ok, msg, 0, {"deleted": 0}
    if kind == "dism_resetbase":
        ok, msg = dism.reset_base()
        return ok, msg, 0, {"deleted": 0}
    if kind == "orphan_apps":
        orphans = (res or {}).get("orphans") or orphan_detector.detect_orphans()
        n, n_del, freed, failed = 0, 0, 0, []
        for o in orphans:
            p = o["path"]
            if protected.is_protected_path(p) or not os.path.exists(p):
                continue
            try:
                if permanent:
                    import shutil
                    if os.path.isdir(p) and not os.path.islink(p):
                        shutil.rmtree(p)
                    else:
                        os.remove(p)
                    n_del += 1
                else:
                    Q.put(p, rule["id"])
                    n += 1
                freed += o.get("size", 0)
            except OSError as e:
                failed.append((p, str(e)))
        if permanent:
            msg = f"Đã xóa vĩnh viễn {n_del} thư mục mồ côi."
        else:
            msg = f"Đã cách ly {n} thư mục mồ côi."
        if failed:
            msg += f" ({len(failed)} lỗi)"
        stats = {"quarantined": n,
                 "quarantined_bytes": 0 if permanent else freed,
                 "deleted": n_del}
        return True, msg, freed, stats
    if kind == "hibernate_off":
        ok, msg = sysclean.hibernate_off()
        return ok, msg, 0, {"deleted": 0}
    if kind == "old_restore_points":
        ok, msg, freed = sysclean.prune_old_restore_points()
        return ok, msg, freed, {"deleted": 0}
    if kind == "docker_prune":
        ok, msg = sysclean.docker_prune()
        return ok, msg, 0, {"deleted": 0}
    if kind == "apt_clean":
        ok, msg, freed = sysclean.apt_clean()
        return ok, msg, freed, {"deleted": 0}
    if kind == "snap_old":
        ok, msg = sysclean.snap_prune_old()
        return ok, msg, 0, {"deleted": 0}
    if kind == "old_kernels":
        ok, msg, freed = sysclean.purge_old_kernels()
        return ok, msg, freed, {"deleted": 0}
    return False, f"special '{kind}' chưa hỗ trợ dọn thật.", 0, {}


def _anchor_of(path: str) -> str:
    r"""Điểm neo để đo disk_usage.

    Windows: ổ đĩa (C:\). Linux: thư mục cha gần nhất còn tồn tại
    (vì file/thư mục sẽ bị xóa sau khi dọn, không đo được nữa).
    """
    ap = os.path.abspath(path)
    if sys.platform == "win32":
        d = os.path.splitdrive(ap)[0]
        return (d + os.sep) if d else "C:\\"
    p = os.path.dirname(ap)
    while p and not os.path.exists(p):
        p = os.path.dirname(p)
    return p or "/"


def _disk_free_map(anchors) -> dict:
    import shutil
    out = {}
    for a in anchors:
        try:
            out[a] = shutil.disk_usage(a).free
        except Exception:  # noqa: BLE001
            pass
    return out


def _anchors_for(results: list, rule_ids: set) -> set:
    anchors = set()
    for res in results:
        if res["rule"]["id"] not in rule_ids:
            continue
        for p in res.get("paths") or []:
            anchors.add(_anchor_of(p))
        for o in res.get("orphans") or []:
            anchors.add(_anchor_of(o["path"]))
    if not anchors:
        anchors.add("C:\\" if sys.platform == "win32" else "/")
    return anchors


def clean_rules(results: list, rule_ids: set, permanent: bool = False,
                level: int = 1) -> dict:
    """Dọn các rule được chọn.

    results: từ scanner.scan_all (đã có paths nếu quét với collect_paths=True).
    Trả về summary dict, gồm "freed_real" là dung lượng ổ đĩa giải phóng
    THỰC TẾ (đo trước/sau bằng disk_usage) — con số này mới là thứ user
    nhìn thấy trong Explorer.
    """
    summary = {"quarantined": 0, "quarantined_bytes": 0, "deleted": 0,
               "failed": [], "freed": 0, "freed_real": None,
               "restore_point": None, "specials": []}

    # Pre-flight: tạo restore point trước mức 2/3 trên Windows
    if level >= 2 and sys.platform == "win32":
        ok, msg = restore_point.create()
        summary["restore_point"] = msg
        action_log.log("restore_point", {"ok": ok, "message": msg})

    # Đo dung lượng trống TRÊN CÁC Ổ ĐĨA CHỨA FILE SẼ DỌN (trước/sau)
    anchors = _anchors_for(results, rule_ids)
    free_before = _disk_free_map(anchors)

    for res in results:
        rule = res["rule"]
        if rule["id"] not in rule_ids:
            continue
        if rule.get("requires_admin") and not privilege.is_admin():
            summary["failed"].append(
                (rule["name"], "cần quyền Admin — đã bỏ qua"))
            continue
        if rule.get("special"):
            ok, msg, freed, stats = _clean_special(rule, res, permanent)
            summary["specials"].append({"rule": rule["name"], "ok": ok,
                                       "message": msg})
            summary["freed"] += freed
            summary["quarantined"] += stats.get("quarantined", 0)
            summary["quarantined_bytes"] += stats.get("quarantined_bytes", 0)
            summary["deleted"] += stats.get("deleted", 0)
            action_log.log("clean_special",
                           {"rule": rule["id"], "ok": ok, "message": msg})
            continue
        # Quét lại full paths nếu kết quả scan không có (scan cũ)
        paths = res.get("paths")
        if paths is None:
            paths = scanner.scan_rule(rule, collect_paths=True).get("paths", [])
        for fp in paths:
            if protected.is_protected_path(fp):
                continue  # kiểm tra lần cuối, không tin mù quáng
            try:
                size = os.path.getsize(fp)
                if permanent:
                    os.remove(fp)
                    summary["deleted"] += 1
                else:
                    Q.put(fp, rule["id"])
                    summary["quarantined"] += 1
                    summary["quarantined_bytes"] += size
                summary["freed"] += size
            except OSError as e:
                summary["failed"].append((fp, str(e)))

    # Đo lại sau khi dọn -> dung lượng giải phóng THỰC TẾ
    free_after = _disk_free_map(anchors)
    real = 0
    for a, before in free_before.items():
        if a in free_after:
            real += max(0, free_after[a] - before)
    summary["freed_real"] = real

    action_log.log("clean", {
        "level": level, "permanent": permanent,
        "rules": sorted(rule_ids),
        "quarantined": summary["quarantined"],
        "quarantined_bytes": summary["quarantined_bytes"],
        "deleted": summary["deleted"],
        "freed_bytes": summary["freed"],
        "freed_real_bytes": summary["freed_real"],
        "failed_count": len(summary["failed"]),
    })
    return summary


def fmt_summary(s: dict) -> str:
    from core.system_info import fmt_gb
    lines = []
    if s["restore_point"]:
        lines.append(f"• Restore point: {s['restore_point']}")
    # Con số quan trọng nhất: dung lượng ổ đĩa giải phóng THỰC TẾ (đo trước/sau)
    if s.get("freed_real") is not None:
        lines.append(f"• 💾 Ổ đĩa đã giải phóng THỰC TẾ: {fmt_gb(s['freed_real'])} "
                     "(đo trực tiếp từ ổ đĩa)")
    if s["deleted"]:
        lines.append(f"• Đã xóa vĩnh viễn: {s['deleted']} file")
    if s["quarantined"]:
        lines.append(f"• Đã chuyển vào khu cách ly: {s['quarantined']} file "
                     f"({fmt_gb(s['quarantined_bytes'])})")
        lines.append("  ⚠️ File cách ly vẫn nằm trên ổ đĩa — CHƯA giải phóng "
                     "dung lượng. Muốn giải phóng, vào tab Khu cách ly → "
                     "Xóa vĩnh viễn.")
    for sp in s["specials"]:
        icon = "✅" if sp["ok"] else "⚠️"
        lines.append(f"• {icon} {sp['rule']}: {sp['message']}")
    if s["failed"]:
        lines.append(f"• Bỏ qua/lỗi: {len(s['failed'])} mục "
                     f"(vd: {s['failed'][0][0]} — {s['failed'][0][1][:80]})")
    if not s["quarantined"] and not s["deleted"] and not s["specials"]:
        lines.append("• Không có gì được dọn.")
    return "\n".join(lines)
