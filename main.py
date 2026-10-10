#!/usr/bin/env python3
"""CleanBoost Phase 1 — CLI.

Quản lý RAM/CPU: xem trạng thái, liệt kê process, kill/force kill,
giải phóng RAM khẩn cấp. Dọn rác: quét thử (dry-run) mức 1.

Chạy:  .venv/bin/python main.py <lệnh> [tùy chọn]
VD:    .venv/bin/python main.py status
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
    sys.exit("Thiếu thư viện psutil. Chạy:  .venv/bin/pip install -r requirements.txt")

from core import privilege, system_info, process_manager, memory_cleaner
from cleaner import scanner
from safety import protected

GB = 1024 ** 3


def bar(pct: float, width: int = 24) -> str:
    fill = max(0, min(width, int(pct / 100 * width)))
    return "█" * fill + "░" * (width - fill)


def fmt_gb(n: float) -> str:
    return f"{n / GB:.1f} GB"


# ------------------------------ lệnh ------------------------------

def cmd_status(_args):
    mem = system_info.memory()
    cpu = system_info.cpu_percent()
    root = "C:\\" if sys.platform == "win32" else "/"
    disk = system_info.disk(root)
    print(f"CleanBoost — trạng thái hệ thống (quyền: {privilege.privilege_label()})")
    print(f"RAM  [{bar(mem['percent'])}] {mem['percent']:5.1f}%  "
          f"{fmt_gb(mem['used'])}/{fmt_gb(mem['total'])} đã dùng")
    print(f"CPU  [{bar(cpu)}] {cpu:5.1f}%  ({system_info.cpu_count()} cores)")
    print(f"Ổ   [{bar(disk['percent'])}] {disk['percent']:5.1f}%  "
          f"{fmt_gb(disk['used'])}/{fmt_gb(disk['total'])} đã dùng")


def cmd_top(args):
    rows = process_manager.list_processes(sort_by=args.sort, limit=args.n)
    print(f"{'PID':>7}  {'RAM':>9}  {'CPU%':>6}  {'USER':<14}  NAME")
    print("-" * 70)
    for r in rows:
        tag = " ⚠️" if r["state"] == "warn" else ""
        print(f"{r['pid']:>7}  {r['rss'] / GB:>8.1f}G  {r['cpu']:>6.1f}  "
              f"{r['user']:<14}  {r['name']}{tag}")
    print(f"\n({len(rows)} process, sắp xếp theo {args.sort}; "
          "process hệ thống nguy hiểm đã được ẩn)")


def cmd_kill(args):
    for pid in args.pid:
        try:
            name = psutil.Process(pid).name() or f"PID {pid}"
        except Exception:  # noqa: BLE001
            name = f"PID {pid}"
        if protected.check_process(name, pid) == "warn" and not args.yes:
            ans = input(
                f"⚠️  {name} (PID {pid}) là process hệ thống nhạy cảm "
                "(kill có thể gây nháy màn hình/mất taskbar tạm thời). "
                "Vẫn kill? [y/N] ").strip().lower()
            if ans != "y":
                print("Đã bỏ qua.")
                continue
        ok, msg = process_manager.kill_process(pid, force=args.force)
        print(msg)


def cmd_freeram(args):
    print("— Dọn RAM nhẹ (không kill process nào) —")
    for m in memory_cleaner.light_clean():
        print(" •", m)
    if args.mode == "light":
        return
    cands = process_manager.emergency_candidates(min_rss_mb=args.min_mb)
    if not cands:
        print(f"\nKhông tìm thấy app nào của bạn ngốn trên {args.min_mb} MB. Xong!")
        return
    print(f"\nTìm thấy {len(cands)} app của bạn đang ngốn RAM:")
    for r in cands:
        print(f"  [{r['pid']}] {r['name']} — {r['rss'] / GB:.1f} GB / CPU {r['cpu']:.1f}%")
    if not args.yes:
        ans = input("Kill TẤT CẢ các app trên? (gõ 'yes' để đồng ý / "
                    "hoặc nhập các PID cách nhau bởi dấu cách để chọn riêng) ").strip()
        if ans.lower() != "yes":
            wanted = {int(x) for x in ans.split() if x.isdigit()}
            cands = [c for c in cands if c["pid"] in wanted]
            if not cands:
                print("Không kill gì cả. Xong!")
                return
    print()
    for r in cands:
        ok, msg = process_manager.kill_process(r["pid"], force=args.force)
        print(" •", msg)
    print("\n— Xả lại RAM sau khi kill —")
    for m in memory_cleaner.light_clean():
        print(" •", m)


def cmd_scan(args):
    print(f"🔍 Quét thử mức {args.level} (dry-run — KHÔNG xóa gì cả)...\n")
    results = scanner.scan_all(args.level)
    total = 0
    for res in results:
        rule = res["rule"]
        if res.get("error"):
            print(f"  ⚪ {rule['name']}: {res['error']}")
            continue
        total += res["size"]
        need_admin = rule.get("requires_admin") and not privilege.is_admin()
        tag = " [cần admin]" if need_admin else ""
        print(f"  📁 {rule['name']}{tag}")
        print(f"     → {res['count']} file, {fmt_gb(res['size'])}"
              + (f"  ({res['note']})" if res.get("note") else ""))
        for s in res["samples"]:
            print(f"       ··· {s}")
    print(f"\n💾 Tổng ước tính có thể thu hồi (mức {args.level}): {fmt_gb(total)}")
    print("Đây là quét thử (dry-run). Dùng lệnh 'clean' để dọn thật "
          "(mặc định vào khu cách ly) hoặc mở GUI.")


def cmd_clean(args):
    from cleaner import engine as _engine
    from cleaner.clean import clean_rules, fmt_summary
    level = args.level
    print(f"🔍 Quét thử mức {level} (dry-run)...\n")
    results = [scanner.scan_rule(r, collect_paths=True)
               for r in _engine.rules_for(level)]
    indexed = [res for res in results if not res.get("error")]
    for i, res in enumerate(indexed, 1):
        rule = res["rule"]
        print(f"  [{i}] {rule['name']} — {res['count']} file, {fmt_gb(res['size'])}")
    if args.all:
        ids = {res["rule"]["id"] for res in indexed if res["size"] > 0}
    else:
        ans = input("Nhập số thứ tự cần dọn (cách nhau bởi dấu cách), hoặc 'all': ").strip()
        if ans.lower() == "all":
            ids = {res["rule"]["id"] for res in indexed if res["size"] > 0}
        else:
            picks = {int(x) for x in ans.split() if x.isdigit()}
            ids = {indexed[i - 1]["rule"]["id"] for i in picks
                   if 1 <= i <= len(indexed)}
    if not ids:
        print("Không chọn gì cả.")
        return
    # Cảnh báo riêng cho rule high-risk (mục 🔴)
    risky = [res["rule"] for res in indexed
             if res["rule"]["id"] in ids and res["rule"].get("risk") == "high"]
    if risky and not args.yes:
        print("\n🔴 CẢNH BÁO — các mục nguy hiểm bạn đã chọn:")
        for r in risky:
            print(f"   • {r['name']}: {r.get('warning', '')}")
        ans = input("Bạn hiểu rủi ro và vẫn tiếp tục? (gõ 'yes') ").strip().lower()
        if ans != "yes":
            print("Đã hủy.")
            return
    permanent = args.permanent
    quarantine_mode = args.quarantine
    if not permanent and not quarantine_mode and not args.yes:
        print("\nChọn cách dọn:")
        print("  [1] XÓA VĨNH VIỄN (khuyên dùng) — giải phóng dung lượng THẬT")
        print("  [2] Chuyển vào khu cách ly — an toàn, khôi phục được,")
        print("      nhưng file vẫn nằm trên ổ đĩa (CHƯA giải phóng GB)")
        ans = input("Chọn [1/2] (mặc định 1): ").strip()
        quarantine_mode = (ans == "2")
        permanent = not quarantine_mode
    elif args.quarantine:
        permanent = False
    if permanent and not args.yes:
        ans = input("⚠️  XÓA VĨNH VIỄN — không khôi phục được. "
                    "Gõ 'yes' để xác nhận: ").strip().lower()
        if ans != "yes":
            print("Đã hủy.")
            return
    print("\nĐang dọn...")
    summary = clean_rules(results, ids, permanent=permanent, level=level)
    print(fmt_summary(summary))


def cmd_quarantine(args):
    from cleaner import quarantine as Q
    if args.qcmd == "list":
        items = Q.list_items()
        if not items:
            print("Khu cách ly trống.")
            return
        for it in items:
            print(f"  [{it['id']}] {it['orig']} — {fmt_gb(it['size'])} — "
                  f"{it.get('quarantined_at', '')[:16]}")
        print(f"\nTổng: {len(items)} file, {fmt_gb(Q.total_size())}")
    elif args.qcmd == "restore":
        ok, msg = Q.restore(args.id)
        print(msg)
    elif args.qcmd == "delete":
        if not args.yes:
            ans = input(f"Xóa vĩnh viễn khỏi khu cách ly: {args.id}? [y/N] ").strip().lower()
            if ans != "y":
                print("Đã hủy.")
                return
        ok, msg = Q.delete_permanent(args.id)
        print(msg)
    elif args.qcmd == "purge":
        n, freed = Q.purge_expired(days=args.days)
        print(f"Đã xóa {n} mục quá {args.days} ngày ({fmt_gb(freed)}).")


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
    print(f"Theo dõi mỗi {args.interval}s — cảnh báo khi RAM>{args.ram}% "
          f"hoặc ổ trống<{args.disk_free}% (Ctrl+C để dừng)")
    alerted, cooldown = {}, 1800
    try:
        while True:
            mem = system_info.memory()
            root = "C:\\" if sys.platform == "win32" else "/"
            disk = system_info.disk(root)
            now = time.time()
            if mem["percent"] >= args.ram and now - alerted.get("ram", 0) > cooldown:
                msg = (f"⚠️ RAM đã dùng {mem['percent']:.0f}% — "
                       "mở CleanBoost để giải phóng!")
                _notify_popup(msg)
                action_log.log("monitor_alert", {"type": "ram", "message": msg})
                alerted["ram"] = now
            free_pct = 100 - disk["percent"]
            if free_pct <= args.disk_free and now - alerted.get("disk", 0) > cooldown:
                msg = (f"⚠️ Ổ {root} chỉ còn trống {free_pct:.0f}% — "
                       "mở CleanBoost để dọn rác!")
                _notify_popup(msg)
                action_log.log("monitor_alert", {"type": "disk", "message": msg})
                alerted["disk"] = now
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nĐã dừng theo dõi.")


# ------------------------------ main ------------------------------

def main():
    ap = argparse.ArgumentParser(
        prog="cleanboost",
        description="CleanBoost — quản lý RAM/CPU & dọn rác (mức 1/2/3).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status", help="Xem RAM / CPU / ổ đĩa realtime")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("top", help="Liệt kê process ngốn tài nguyên nhất")
    p.add_argument("-n", type=int, default=15, help="Số process hiện (mặc định 15)")
    p.add_argument("--sort", choices=["memory", "cpu"], default="memory")
    p.set_defaults(fn=cmd_top)

    p = sub.add_parser("kill", help="Kill / force kill process theo PID")
    p.add_argument("pid", type=int, nargs="+", help="Một hoặc nhiều PID")
    p.add_argument("--force", action="store_true", help="Force kill (kết thúc ngay)")
    p.add_argument("--yes", action="store_true", help="Bỏ qua hỏi lại với process warn")
    p.set_defaults(fn=cmd_kill)

    p = sub.add_parser("freeram", help="Giải phóng RAM")
    p.add_argument("--mode", choices=["light", "standard"], default="light",
                   help="light: chỉ xả cache RAM, không kill | "
                        "standard: + kill app ngốn RAM (có hỏi trước)")
    p.add_argument("--min-mb", type=int, default=200,
                   help="Ngưỡng RAM (MB) để coi là ứng viên kill (mặc định 200)")
    p.add_argument("--force", action="store_true", help="Force kill khi kill app")
    p.add_argument("--yes", action="store_true", help="Kill tất cả ứng viên, không hỏi")
    p.set_defaults(fn=cmd_freeram)

    p = sub.add_parser("scan", help="Quét thử file rác (không xóa gì)")
    p.add_argument("--level", type=int, choices=[1, 2, 3], default=1,
                   help="Mức quét: 1=tiêu chuẩn, 2=nâng cao, 3=chuyên sâu")
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("clean", help="Dọn thật (xóa để giải phóng dung lượng)")
    p.add_argument("--level", type=int, choices=[1, 2, 3], default=1)
    p.add_argument("--all", action="store_true",
                   help="Dọn tất cả nhóm tìm thấy, không hỏi chọn")
    p.add_argument("--permanent", action="store_true",
                   help="Xóa vĩnh viễn để giải phóng dung lượng (không hỏi)")
    p.add_argument("--quarantine", action="store_true",
                   help="Chỉ chuyển vào khu cách ly (an toàn, chưa giải phóng GB)")
    p.add_argument("--yes", action="store_true", help="Bỏ qua mọi xác nhận")
    p.set_defaults(fn=cmd_clean)

    p = sub.add_parser("quarantine", help="Quản lý khu cách ly")
    qs = p.add_subparsers(dest="qcmd", required=True)
    qs.add_parser("list", help="Liệt kê file trong khu cách ly")
    q = qs.add_parser("restore", help="Khôi phục 1 file về chỗ cũ")
    q.add_argument("id", help="ID trong khu cách ly")
    q = qs.add_parser("delete", help="Xóa vĩnh viễn 1 file trong khu cách ly")
    q.add_argument("id", help="ID trong khu cách ly")
    q.add_argument("--yes", action="store_true")
    q = qs.add_parser("purge", help="Xóa các mục quá hạn")
    q.add_argument("--days", type=int, default=14)
    p.set_defaults(fn=cmd_quarantine)

    p = sub.add_parser("schedule", help="Lịch dọn tự động định kỳ")
    ss = p.add_subparsers(dest="scmd", required=True)
    ss.add_parser("install", help="Đăng ký dọn tự động mỗi Chủ nhật 03:00")
    ss.add_parser("remove", help="Gỡ lịch dọn tự động")
    ss.add_parser("status", help="Xem trạng thái lịch")
    p.set_defaults(fn=cmd_schedule)

    p = sub.add_parser("monitor", help="Theo dõi RAM/ổ đĩa, cảnh báo khi đầy")
    p.add_argument("--interval", type=int, default=60,
                   help="Giây giữa các lần kiểm tra (mặc định 60)")
    p.add_argument("--ram", type=int, default=90,
                   help="Cảnh báo khi RAM >= N% (mặc định 90)")
    p.add_argument("--disk-free", type=int, default=10,
                   help="Cảnh báo khi ổ trống <= N% (mặc định 10)")
    p.set_defaults(fn=cmd_monitor)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
