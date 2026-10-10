#!/usr/bin/env python3
"""CleanBoost — dọn tự động định kỳ (headless, không cần người bấm).

Quét mức 1, chỉ dọn các rule low-risk + default_on, LUÔN vào khu cách ly.
Dùng cho Task Scheduler (Windows) / cron (Linux).

    python auto_clean.py [--dry-run] [--level 1]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cleaner import engine, scanner
from cleaner.clean import clean_rules, fmt_summary
from cleaner import action_log
from core import privilege, system_info


def main():
    ap = argparse.ArgumentParser(description="CleanBoost auto clean (headless)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Chỉ in ra sẽ dọn gì, không dọn thật")
    ap.add_argument("--level", type=int, choices=[1, 2, 3], default=1)
    args = ap.parse_args()

    admin = privilege.is_admin()
    print(f"[auto_clean] Quét mức {args.level} (quyền: {privilege.privilege_label()})...")
    results = [scanner.scan_rule(r, collect_paths=True)
               for r in engine.rules_for(args.level)]

    # Chỉ dọn rule: default_on + low risk + (đủ quyền)
    ids = {res["rule"]["id"] for res in results
           if not res.get("error") and res["size"] > 0
           and res["rule"].get("default_on")
           and res["rule"].get("risk") == "low"
           and (admin or not res["rule"].get("requires_admin"))}
    total = sum(res["size"] for res in results
                if res["rule"]["id"] in ids)
    print(f"[auto_clean] Sẽ dọn {len(ids)} nhóm, ~{total / 1024**3:.2f} GB "
          f"(vào khu cách ly).")
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
