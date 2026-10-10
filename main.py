#!/usr/bin/env python3
"""CleanBoost — CLI.

Manage RAM/CPU: status, list processes, kill/force kill,
emergency RAM release. Clean junk: dry-run scan at levels 1-3.

Run:  .venv/bin/python main.py <command> [options]
Eg:   .venv/bin/python main.py status
      .venv/bin/python main.py top -n 10
      .venv/bin/python main.py kill 1234 --force
      .venv/bin/python main.py freeram --mode standard
      .venv/bin/python main.py scan --level 1
"""
import argparse
import sys

try:
    import psutil  # noqa: F401
except ImportError:
    sys.exit("Missing psutil library. Run:  .venv/bin/pip install -r requirements.txt")

from core import privilege, system_info, process_manager, memory_cleaner
from cleaner import scanner
from safety import protected

GB = 1024 ** 3


def bar(pct: float, width: int = 24) -> str:
    fill = max(0, min(width, int(pct / 100 * width)))
    return "█" * fill + "░" * (width - fill)


def fmt_gb(n: float) -> str:
    return f"{n / GB:.1f} GB"


# ------------------------------ commands ------------------------------

def cmd_status(_args):
    mem = system_info.memory()
    cpu = system_info.cpu_percent()
    root = "C:\\" if sys.platform == "win32" else "/"
    disk = system_info.disk(root)
    print(f"CleanBoost - system status (rights: {privilege.privilege_label()})")
    print(f"RAM  [{bar(mem['percent'])}] {mem['percent']:5.1f}%  "
          f"{fmt_gb(mem['used'])}/{fmt_gb(mem['total'])} used")
    print(f"CPU  [{bar(cpu)}] {cpu:5.1f}%  ({system_info.cpu_count()} cores)")
    print(f"Disk [{bar(disk['percent'])}] {disk['percent']:5.1f}%  "
          f"{fmt_gb(disk['used'])}/{fmt_gb(disk['total'])} used")


def cmd_top(args):
    rows = process_manager.list_processes(sort_by=args.sort, limit=args.n)
    print(f"{'PID':>7}  {'RAM':>9}  {'CPU%':>6}  {'USER':<14}  NAME")
    print("-" * 70)
    for r in rows:
        tag = " ⚠️" if r["state"] == "warn" else ""
        print(f"{r['pid']:>7}  {r['rss'] / GB:>8.1f}G  {r['cpu']:>6.1f}  "
              f"{r['user']:<14}  {r['name']}{tag}")
    print(f"\n({len(rows)} processes, sorted by {args.sort}; "
          "dangerous system processes are hidden)")


def cmd_kill(args):
    for pid in args.pid:
        try:
            name = psutil.Process(pid).name() or f"PID {pid}"
        except Exception:  # noqa: BLE001
            name = f"PID {pid}"
        if protected.check_process(name, pid) == "warn" and not args.yes:
            ans = input(
                f"WARNING: {name} (PID {pid}) is a sensitive system process "
                "(killing it may flicker the screen / hide the taskbar briefly). "
                "Kill anyway? [y/N] ").strip().lower()
            if ans != "y":
                print("Skipped.")
                continue
        ok, msg = process_manager.kill_process(pid, force=args.force)
        print(msg)


def cmd_freeram(args):
    print("— Light RAM clean (no process will be closed) —")
    for m in memory_cleaner.light_clean():
        print(" •", m)
    if args.mode == "light":
        return
    cands = process_manager.emergency_candidates(min_rss_mb=args.min_mb)
    if not cands:
        print(f"\nNo app of yours is using over {args.min_mb} MB. Done!")
        return
    print(f"\nFound {len(cands)} of your apps using heavy RAM:")
    for r in cands:
        print(f"  [{r['pid']}] {r['name']} — {r['rss'] / GB:.1f} GB / CPU {r['cpu']:.1f}%")
    if not args.yes:
        ans = input("Kill ALL apps above? (type 'yes' to confirm / "
                    "or enter specific PIDs separated by spaces) ").strip()
        if ans.lower() != "yes":
            wanted = {int(x) for x in ans.split() if x.isdigit()}
            cands = [c for c in cands if c["pid"] in wanted]
            if not cands:
                print("Nothing killed. Done!")
                return
    print()
    for r in cands:
        ok, msg = process_manager.kill_process(r["pid"], force=args.force)
        print(" •", msg)
    print("\n— Flushing RAM after kill —")
    for m in memory_cleaner.light_clean():
        print(" •", m)


def cmd_scan(args):
    print(f"Scanning level {args.level} (dry-run — NOTHING will be deleted)...\n")
    results = scanner.scan_all(args.level)
    total = 0
    for res in results:
        rule = res["rule"]
        if res.get("error"):
            print(f"  ⚪ {rule['name']}: {res['error']}")
            continue
        total += res["size"]
        need_admin = rule.get("requires_admin") and not privilege.is_admin()
        tag = " [needs admin]" if need_admin else ""
        print(f"  📁 {rule['name']}{tag}")
        print(f"     → {res['count']} file, {fmt_gb(res['size'])}"
              + (f"  ({res['note']})" if res.get("note") else ""))
        for s in res["samples"]:
            print(f"       ··· {s}")
    print(f"\nEstimated reclaimable (level {args.level}): {fmt_gb(total)}")
    print("This was a dry-run. Use the 'clean' command for real cleanup "
          "or open the GUI.")


def cmd_clean(args):
    from cleaner import engine as _engine
    from cleaner.clean import clean_rules, fmt_summary
    level = args.level
    print(f"Scanning level {level} (dry-run)...\n")
    results = [scanner.scan_rule(r, collect_paths=True)
               for r in _engine.rules_for(level)]
    indexed = [res for res in results if not res.get("error")]
    for i, res in enumerate(indexed, 1):
        rule = res["rule"]
        print(f"  [{i}] {rule['name']} — {res['count']} file, {fmt_gb(res['size'])}")
    if args.all:
        ids = {res["rule"]["id"] for res in indexed if res["size"] > 0}
    else:
        ans = input("Enter numbers to clean (separated by spaces), or 'all': ").strip()
        if ans.lower() == "all":
            ids = {res["rule"]["id"] for res in indexed if res["size"] > 0}
        else:
            picks = {int(x) for x in ans.split() if x.isdigit()}
            ids = {indexed[i - 1]["rule"]["id"] for i in picks
                   if 1 <= i <= len(indexed)}
    if not ids:
        print("Nothing selected.")
        return
    # Cảnh báo riêng cho rule high-risk (mục 🔴)
    risky = [res["rule"] for res in indexed
             if res["rule"]["id"] in ids and res["rule"].get("risk") == "high"]
    if risky and not args.yes:
        print("\nHIGH-RISK WARNING — you selected:")
        for r in risky:
            print(f"   • {r['name']}: {r.get('warning', '')}")
        ans = input("You understand the risk and want to continue? (type 'yes') ").strip().lower()
        if ans != "yes":
            print("Cancelled.")
            return
    permanent = args.permanent
    quarantine_mode = args.quarantine
    if not permanent and not quarantine_mode and not args.yes:
        print("\nChoose cleanup mode:")
        print("  [1] DELETE PERMANENTLY (recommended) — frees REAL disk space")
        print("  [2] Move to quarantine — safe and restorable,")
        print("      but files stay on disk (does NOT free space yet)")
        ans = input("Choose [1/2] (default 1): ").strip()
        quarantine_mode = (ans == "2")
        permanent = not quarantine_mode
    elif args.quarantine:
        permanent = False
    if permanent and not args.yes:
        ans = input("PERMANENT DELETE — cannot be recovered. "
                    "Type 'yes' to confirm: ").strip().lower()
        if ans != "yes":
            print("Cancelled.")
            return
    print("\nCleaning...")
    summary = clean_rules(results, ids, permanent=permanent, level=level)
    print(fmt_summary(summary))


def cmd_quarantine(args):
    from cleaner import quarantine as Q
    if args.qcmd == "list":
        items = Q.list_items()
        if not items:
            print("Quarantine is empty.")
            return
        for it in items:
            print(f"  [{it['id']}] {it['orig']} — {fmt_gb(it['size'])} — "
                  f"{it.get('quarantined_at', '')[:16]}")
        print(f"\nTotal: {len(items)} file(s), {fmt_gb(Q.total_size())}")
    elif args.qcmd == "restore":
        ok, msg = Q.restore(args.id)
        print(msg)
    elif args.qcmd == "delete":
        if not args.yes:
            ans = input(f"Permanently delete from quarantine: {args.id}? [y/N] ").strip().lower()
            if ans != "y":
                print("Cancelled.")
                return
        ok, msg = Q.delete_permanent(args.id)
        print(msg)
    elif args.qcmd == "purge":
        n, freed = Q.purge_expired(days=args.days)
        print(f"Deleted {n} item(s) older than {args.days} days ({fmt_gb(freed)}).")


def cmd_schedule(args):
    from cleaner import scheduler
    if args.scmd == "install":
        ok, msg = scheduler.install()
    elif args.scmd == "remove":
        ok, msg = scheduler.remove()
    else:
        ok, msg = scheduler.status()
    print(msg)


def _notify_popup(msg: str):
    """Popup cảnh báo (Windows MessageBox / notify-send / console)."""
    import ctypes
    import shutil
    import subprocess
    print(msg, flush=True)
    try:
        if sys.platform == "win32":
            ctypes.windll.user32.MessageBoxW(None, msg, "CleanBoost", 0x40)
        elif shutil.which("notify-send"):
            subprocess.run(["notify-send", "CleanBoost", msg])
    except Exception:  # noqa: BLE001
        pass


def cmd_monitor(args):
    import time
    from cleaner import action_log
    print(f"Monitoring every {args.interval}s — alert when RAM>{args.ram}% "
          f"or disk free<{args.disk_free}% (Ctrl+C to stop)")
    alerted, cooldown = {}, 1800
    try:
        while True:
            mem = system_info.memory()
            root = "C:\\" if sys.platform == "win32" else "/"
            disk = system_info.disk(root)
            now = time.time()
            if mem["percent"] >= args.ram and now - alerted.get("ram", 0) > cooldown:
                msg = (f"WARNING: RAM is {mem['percent']:.0f}% full — "
                       "open CleanBoost to free RAM!")
                _notify_popup(msg)
                action_log.log("monitor_alert", {"type": "ram", "message": msg})
                alerted["ram"] = now
            free_pct = 100 - disk["percent"]
            if free_pct <= args.disk_free and now - alerted.get("disk", 0) > cooldown:
                msg = (f"WARNING: drive {root} only {free_pct:.0f}% free — "
                       "open CleanBoost to clean junk!")
                _notify_popup(msg)
                action_log.log("monitor_alert", {"type": "disk", "message": msg})
                alerted["disk"] = now
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")


# ------------------------------ main ------------------------------

def main():
    ap = argparse.ArgumentParser(
        prog="cleanboost",
        description="CleanBoost — manage RAM/CPU and clean junk (levels 1/2/3).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status", help="Show realtime RAM / CPU / disk")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("top", help="List the most resource-hungry processes")
    p.add_argument("-n", type=int, default=15, help="Number of processes to show (default 15)")
    p.add_argument("--sort", choices=["memory", "cpu"], default="memory")
    p.set_defaults(fn=cmd_top)

    p = sub.add_parser("kill", help="Kill / force kill processes by PID")
    p.add_argument("pid", type=int, nargs="+", help="One or more PIDs")
    p.add_argument("--force", action="store_true", help="Force kill (terminate immediately)")
    p.add_argument("--yes", action="store_true", help="Skip confirmation for sensitive processes")
    p.set_defaults(fn=cmd_kill)

    p = sub.add_parser("freeram", help="Free up RAM")
    p.add_argument("--mode", choices=["light", "standard"], default="light",
                   help="light: flush RAM cache only, no kill | "
                        "standard: also kill RAM-hungry apps (asks first)")
    p.add_argument("--min-mb", type=int, default=200,
                   help="RAM threshold (MB) to consider an app a kill candidate (default 200)")
    p.add_argument("--force", action="store_true", help="Force kill when closing apps")
    p.add_argument("--yes", action="store_true", help="Kill all candidates without asking")
    p.set_defaults(fn=cmd_freeram)

    p = sub.add_parser("scan", help="Dry-run junk scan (deletes nothing)")
    p.add_argument("--level", type=int, choices=[1, 2, 3], default=1,
                   help="Scan level: 1=standard, 2=advanced, 3=deep")
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("clean", help="Real cleanup (delete to free space)")
    p.add_argument("--level", type=int, choices=[1, 2, 3], default=1)
    p.add_argument("--all", action="store_true",
                   help="Clean all found groups without asking")
    p.add_argument("--permanent", action="store_true",
                   help="Delete permanently to free space (no prompt)")
    p.add_argument("--quarantine", action="store_true",
                   help="Only move to quarantine (safe, does not free space yet)")
    p.add_argument("--yes", action="store_true", help="Skip all confirmations")
    p.set_defaults(fn=cmd_clean)

    p = sub.add_parser("quarantine", help="Manage the quarantine")
    qs = p.add_subparsers(dest="qcmd", required=True)
    qs.add_parser("list", help="List files in quarantine")
    q = qs.add_parser("restore", help="Restore one file to its original location")
    q.add_argument("id", help="Quarantine ID")
    q = qs.add_parser("delete", help="Permanently delete one quarantined file")
    q.add_argument("id", help="Quarantine ID")
    q.add_argument("--yes", action="store_true")
    q = qs.add_parser("purge", help="Delete expired items")
    q.add_argument("--days", type=int, default=14)
    p.set_defaults(fn=cmd_quarantine)

    p = sub.add_parser("schedule", help="Automatic cleanup schedule")
    ss = p.add_subparsers(dest="scmd", required=True)
    ss.add_parser("install", help="Schedule automatic cleanup every Sunday 03:00")
    ss.add_parser("remove", help="Remove the automatic schedule")
    ss.add_parser("status", help="Show schedule status")
    p.set_defaults(fn=cmd_schedule)

    p = sub.add_parser("monitor", help="Monitor RAM/disk, alert when full")
    p.add_argument("--interval", type=int, default=60,
                   help="Seconds between checks (default 60)")
    p.add_argument("--ram", type=int, default=90,
                   help="Alert when RAM >= N% (default 90)")
    p.add_argument("--disk-free", type=int, default=10,
                   help="Alert when free disk <= N% (default 10)")
    p.set_defaults(fn=cmd_monitor)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
