#!/usr/bin/env python3
"""CleanBoost — automatic periodic cleanup (headless).

Scans level 1, cleans only low-risk + default_on rules, ALWAYS to quarantine.
Used by Task Scheduler (Windows) / cron (Linux).

    python auto_clean.py [--dry-run] [--level 1]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cleaner import engine, scanner
from cleaner.clean import clean_rules, fmt_summary
from cleaner import action_log
from core import privilege


def main():
    ap = argparse.ArgumentParser(description="CleanBoost auto clean (headless)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Only print what would be cleaned, no real cleanup")
    ap.add_argument("--level", type=int, choices=[1, 2, 3], default=1)
    args = ap.parse_args()

    admin = privilege.is_admin()
    print(f"[auto_clean] Scanning level {args.level} (rights: {privilege.privilege_label()})...")
    results = [scanner.scan_rule(r, collect_paths=True)
               for r in engine.rules_for(args.level)]

    # Chỉ dọn rule: default_on + low risk + (đủ quyền)
    # Bug #3 fix: include action-specials (size 0 by design — they run a command).
    # Match size>0 OR has note (DISM component cleanup, docker prune, snap prune).
    ids = {res["rule"]["id"] for res in results
           if not res.get("error")
           and (res["size"] > 0 or res.get("note"))
           and res["rule"].get("default_on")
           and res["rule"].get("risk") == "low"
           and (admin or not res["rule"].get("requires_admin"))}
    total = sum(res["size"] for res in results
                if res["rule"]["id"] in ids)
    print(f"[auto_clean] Will clean {len(ids)} group(s), ~{total / 1024**3:.2f} GB "
          f"(to quarantine).")
    action_log.log("auto_clean_scan", {"level": args.level,
                                       "groups": len(ids),
                                       "bytes": total,
                                       "dry_run": args.dry_run})
    if args.dry_run or not ids:
        return
    summary = clean_rules(results, ids, permanent=False, level=args.level)
    print(fmt_summary(summary))


if __name__ == "__main__":
    main()
