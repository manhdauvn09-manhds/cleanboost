"""Bandwidth Hog Finder (CleanBoost v2.5, A.6).

Measures total up/down throughput (net_io_counters, two snapshots)
and lists the apps holding the most ACTIVE connections right now,
so the user can see what is using the network and end it.

Honest limit: psutil cannot attribute bytes to individual processes,
so per-app rows are ranked by ACTIVE CONNECTION count, not by
per-app bytes. The total up/down rate is real measured throughput.

Read-only (listing). Ending a task goes through process_manager and
the protection layer in the UI. Never raises.
"""
import time

import psutil


def _snapshot():
    try:
        counters = psutil.net_io_counters(pernic=True)
        total_sent = sum(c.bytes_sent for c in counters.values())
        total_recv = sum(c.bytes_recv for c in counters.values())
        return total_sent, total_recv
    except Exception:
        return 0, 0


def get_bandwidth_hogs(interval=3.0):
    """Return (ok, message, data).

    data = {"sent_per_sec": bytes/s, "recv_per_sec": bytes/s,
            "rows": [{pid, process, connections, remote_ips}]}.
    """
    try:
        sent0, recv0 = _snapshot()
        time.sleep(max(0.5, min(interval, 10.0)))
        sent1, recv1 = _snapshot()
        elapsed = max(interval, 0.5)
        data = {
            "sent_per_sec": (sent1 - sent0) / elapsed,
            "recv_per_sec": (recv1 - recv0) / elapsed,
            "rows": [],
        }
        by_pid = {}
        try:
            conns = psutil.net_connections(kind="inet")
        except Exception:
            conns = []
        name_cache = {}
        for c in conns:
            try:
                if getattr(c, "status", "") not in ("ESTABLISHED", "CLOSE_WAIT"):
                    continue
                pid = getattr(c, "pid", None)
                if not pid:
                    continue
                if pid not in name_cache:
                    try:
                        name_cache[pid] = psutil.Process(pid).name() or "unknown"
                    except Exception:
                        name_cache[pid] = "unknown"
                row = by_pid.setdefault(pid, {
                    "pid": pid, "process": name_cache[pid],
                    "connections": 0, "remote_ips": []})
                row["connections"] += 1
                raddr = getattr(c, "raddr", None)
                if raddr and getattr(raddr, "ip", None):
                    if raddr.ip not in row["remote_ips"]:
                        row["remote_ips"].append(raddr.ip)
            except Exception:
                continue
        rows = sorted(by_pid.values(),
                      key=lambda r: r["connections"], reverse=True)
        data["rows"] = rows[:30]
        if not rows:
            return True, "No app is holding an active connection right now.", data
        top = rows[0]
        return (True,
                f"Total: {data['recv_per_sec'] / 1024:.0f} KB/s down, "
                f"{data['sent_per_sec'] / 1024:.0f} KB/s up. Most active: "
                f"{top['process']} ({top['connections']} connection(s)).",
                data)
    except Exception as e:  # noqa: BLE001
        return False, f"Could not measure bandwidth: {e}", {
            "sent_per_sec": 0, "recv_per_sec": 0, "rows": []}
