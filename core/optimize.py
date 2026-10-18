"""Optimize in 1 Click (CleanBoost v2.4, B.1).

Safe chain only:
  1. Light RAM clean (kills nothing)
  2. Scan + clean level 1, default_on groups only, to QUARANTINE
     (never permanent delete — the user confirms permanent deletes
     group by group in the Disk Cleaner tab)
  3. Quick Refresh (flushdns / release / renew)

Ping to 1.1.1.1 is measured before and after for the report.
Never raises — returns (ok, message, report).
"""
from cleaner import action_log
from core import memory_cleaner, system_info


def _ping():
    try:
        from network import speed as net_speed
        _ok, _msg, ms = net_speed.ping_host("1.1.1.1", count=2)
        return ms
    except Exception:
        return None


def run_optimize(progress_cb=None):
    """Run the safe optimize chain. Returns (ok, message, report)."""
    report = {
        "ram_before_pct": None, "ram_after_pct": None,
        "disk_freed_real_bytes": 0, "quarantined_files": 0,
        "quarantined_bytes": 0, "deleted_files": 0,
        "refresh_ok": None, "refresh_steps": [],
        "ping_before_ms": None, "ping_after_ms": None,
        "messages": [],
    }
    try:
        if progress_cb:
            progress_cb(0, 100, "Measuring ping (before)")
        report["ping_before_ms"] = _ping()
        try:
            mem = system_info.memory()
            report["ram_before_pct"] = round(mem["percent"], 1)
        except Exception:
            pass

        # Step 1 — Light RAM clean (0-25%)
        if progress_cb:
            progress_cb(5, 100, "Light RAM clean")
        try:
            msgs = memory_cleaner.light_clean()
            report["messages"].extend(msgs)
        except Exception as e:  # noqa: BLE001
            report["messages"].append(f"Light RAM clean failed: {e}")

        # Step 2 — scan + quarantine level 1 default_on groups (25-70%)
        if progress_cb:
            progress_cb(30, 100, "Scanning junk (level 1)")
        try:
            from cleaner import engine, scanner
            from cleaner.clean import clean_rules
            results = [scanner.scan_rule(r, collect_paths=True)
                       for r in engine.rules_for(1)]
            ids = {res["rule"]["id"] for res in results
                   if res["rule"].get("default_on")
                   and res.get("size", 0) > 0 and not res.get("error")}
            if ids:
                if progress_cb:
                    progress_cb(55, 100, "Moving junk to quarantine")
                summary = clean_rules(results, ids, permanent=False, level=1)
                report["disk_freed_real_bytes"] = summary.get("freed_real") or 0
                report["quarantined_files"] = summary.get("quarantined", 0)
                report["quarantined_bytes"] = summary.get("quarantined_bytes", 0)
                report["deleted_files"] = summary.get("deleted", 0)
                if summary.get("failed"):
                    report["messages"].append(
                        f"{len(summary['failed'])} group(s) skipped "
                        "(e.g. needs Admin).")
            else:
                report["messages"].append("No level-1 junk found to clean.")
        except Exception as e:  # noqa: BLE001
            report["messages"].append(f"Disk clean failed: {e}")

        # Step 3 — Quick Refresh (70-95%)
        if progress_cb:
            progress_cb(75, 100, "Quick Refresh")
        try:
            from network.refresh import quick_refresh

            def _sub(i, total, label):
                if progress_cb:
                    progress_cb(75 + int(20 * i / max(total, 1)), 100,
                                f"Quick Refresh: {label}")

            ok, msg, steps = quick_refresh(progress_cb=_sub)
            report["refresh_ok"] = ok
            report["refresh_steps"] = steps
            report["messages"].append(msg)
        except Exception as e:  # noqa: BLE001
            report["refresh_ok"] = False
            report["messages"].append(f"Quick Refresh failed: {e}")

        try:
            mem = system_info.memory()
            report["ram_after_pct"] = round(mem["percent"], 1)
        except Exception:
            pass
        if progress_cb:
            progress_cb(97, 100, "Measuring ping (after)")
        report["ping_after_ms"] = _ping()
        if progress_cb:
            progress_cb(100, 100, "Done")

        action_log.log("optimize", {
            "ram_before_pct": report["ram_before_pct"],
            "ram_after_pct": report["ram_after_pct"],
            "quarantined_files": report["quarantined_files"],
            "quarantined_bytes": report["quarantined_bytes"],
            "freed_real_bytes": report["disk_freed_real_bytes"],
            "refresh_ok": report["refresh_ok"],
            "ping_before_ms": report["ping_before_ms"],
            "ping_after_ms": report["ping_after_ms"],
        })

        parts = []
        if report["ram_before_pct"] is not None and report["ram_after_pct"] is not None:
            parts.append(f"RAM {report['ram_before_pct']:.0f}% -> "
                         f"{report['ram_after_pct']:.0f}%")
        if report["quarantined_files"]:
            gb = report["quarantined_bytes"] / (1024 ** 3)
            parts.append(f"{report['quarantined_files']} junk group file(s) "
                         f"({gb:.2f} GB) moved to quarantine")
        if report["ping_before_ms"] is not None and report["ping_after_ms"] is not None:
            parts.append(f"ping {report['ping_before_ms']:.0f} ms -> "
                         f"{report['ping_after_ms']:.0f} ms")
        summary = "Optimize done: " + ("; ".join(parts) if parts else "nothing changed.")
        if report["refresh_ok"] is False:
            summary += " (Warning: Quick Refresh failed — see details.)"
        return True, summary, report
    except Exception as e:  # noqa: BLE001 — never raise
        return False, f"Optimize failed: {e}", report


def format_report(report):
    """Multi-line English report for the UI."""
    lines = []
    if report.get("ram_before_pct") is not None:
        lines.append(f"RAM: {report['ram_before_pct']:.0f}% -> "
                     f"{report.get('ram_after_pct', '-')}%")
    lines.append(f"Junk quarantined: {report.get('quarantined_files', 0)} file(s) "
                 f"({report.get('quarantined_bytes', 0) / (1024 ** 3):.2f} GB)")
    lines.append("Note: quarantined files still occupy disk space until you "
                 "delete them permanently from the Quarantine tab.")
    if report.get("refresh_ok") is not None:
        lines.append("Quick Refresh: "
                     + ("OK" if report["refresh_ok"] else "FAILED"))
        for s in report.get("refresh_steps") or []:
            lines.append(f"  - {s['step']}: "
                         + ("OK" if s["ok"] else f"FAILED — {s['message']}"))
    pb, pa = report.get("ping_before_ms"), report.get("ping_after_ms")
    lines.append("Ping 1.1.1.1: "
                 + (f"{pb:.0f} ms -> {pa:.0f} ms" if pb is not None and pa is not None
                    else "not measured"))
    for m in report.get("messages") or []:
        if m and m not in lines:
            lines.append(f"• {m}")
    return "\n".join(lines)
