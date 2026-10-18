"""Network Diagnostics (CleanBoost v2.5, A.10).

Runs 4 checks and applies exclusion logic to conclude where the
problem is, so the user does not have to guess:

- gateway ping high/unreachable -> WiFi/LAN problem
- gateway OK + external ping high -> ISP / international route
- DNS resolve slow -> DNS problem (try DNS Switcher)
- everything OK -> network fine, lag is from the app/server

Read-only. Never raises — returns (ok, message, data).
"""
import psutil

from network import info as net_info
from network import speed as net_speed

GATEWAY_SLOW_MS = 100.0
EXTERNAL_SLOW_MS = 200.0
DNS_SLOW_MS = 500.0


def _check(name, ok, value, detail):
    return {"name": name, "ok": ok, "value": value, "detail": detail}


def run_diagnostics():
    """Run all checks. Returns (ok, message, data).

    data = {"checks": [...], "conclusion": str,
            "established_count": int, "top_ips": [...]}.
    """
    try:
        _ok, _msg, net = net_info.get_network_info()
        gateway = net.get("gateway", "")
        checks = []

        # 1. Gateway ping
        if gateway:
            ok, _m, ms = net_speed.ping_host(gateway, count=2)
            if ok and ms is not None and ms <= GATEWAY_SLOW_MS:
                checks.append(_check("Ping gateway (router)", True, ms,
                                     f"{ms:.0f} ms — local network is fine."))
            elif ok and ms is not None:
                checks.append(_check("Ping gateway (router)", False, ms,
                                     f"{ms:.0f} ms — slow local network."))
            else:
                checks.append(_check("Ping gateway (router)", False, None,
                                     "No reply — WiFi/LAN problem."))
        else:
            checks.append(_check("Ping gateway (router)", False, None,
                                 "Gateway unknown."))

        # 2. External pings
        ext = []
        for host in ("1.1.1.1", "8.8.8.8"):
            ok, _m, ms = net_speed.ping_host(host, count=2)
            ext.append(ms if ok else None)
            checks.append(_check(f"Ping {host}", bool(ok and ms is not None),
                                 ms,
                                 f"{ms:.0f} ms." if ms is not None
                                 else "No reply."))
        ext_ok = [v for v in ext if v is not None]

        # 3. DNS resolve time
        ok, _m, dns_ms = net_speed.measure_dns_time("google.com")
        checks.append(_check("DNS resolve time", bool(ok and dns_ms is not None),
                             dns_ms,
                             f"{dns_ms:.0f} ms." if dns_ms is not None
                             else "Resolve failed."))

        # 4. Established connections + top remote IPs
        established = 0
        ip_counts = {}
        try:
            for c in psutil.net_connections(kind="inet"):
                if getattr(c, "status", "") != "ESTABLISHED":
                    continue
                established += 1
                raddr = getattr(c, "raddr", None)
                if raddr and getattr(raddr, "ip", None):
                    ip_counts[raddr.ip] = ip_counts.get(raddr.ip, 0) + 1
        except Exception:
            pass
        top_ips = sorted(ip_counts.items(), key=lambda kv: kv[1],
                         reverse=True)[:5]
        checks.append(_check("Established connections", True, established,
                             f"{established} connection(s); top remote IP: "
                             + (top_ips[0][0] if top_ips else "-")))

        # 5. WiFi signal (only when on WiFi)
        wifi = net.get("wifi")
        if wifi:
            sig = wifi.get("signal_percent")
            checks.append(_check("WiFi signal", bool(sig is not None and sig >= 50),
                                 sig,
                                 f"{sig}% on {wifi.get('ssid', '')}."
                                 if sig is not None else "Unknown."))

        # Conclusion by exclusion (ke-hoach-v3, A.10).
        gw = checks[0]
        if not gw["ok"]:
            conclusion = ("WiFi/LAN problem — move closer to the router, "
                          "check the cable, or run Adapter Reset.")
        elif ext_ok and max(ext_ok) > EXTERNAL_SLOW_MS:
            conclusion = ("Local network is OK but international ping is "
                          "high — ISP / route issue. Try Quick Refresh.")
        elif dns_ms is not None and dns_ms > DNS_SLOW_MS:
            conclusion = ("DNS is slow — try the DNS Switcher (measure "
                          "fastest DNS first).")
        elif ext_ok and min(ext_ok) is not None and min(ext_ok) <= EXTERNAL_SLOW_MS:
            conclusion = ("Network looks fine — the lag is probably from "
                          "the app / game server itself.")
        else:
            conclusion = ("Could not reach the internet — check the cable / "
                          "WiFi, then try Quick Refresh.")

        data = {"checks": checks, "conclusion": conclusion,
                "established_count": established,
                "top_ips": [{"ip": ip, "connections": n}
                            for ip, n in top_ips]}
        return True, conclusion, data
    except Exception as e:  # noqa: BLE001
        return False, f"Diagnostics failed: {e}", {"checks": [],
                                                    "conclusion": ""}


def format_diagnostics(data):
    """Multi-line English report for the UI."""
    lines = []
    for c in data.get("checks", []):
        icon = "OK " if c["ok"] else "!  "
        lines.append(f"{icon}{c['name']}: {c['detail']}")
    lines.append("")
    lines.append("Conclusion: " + data.get("conclusion", ""))
    return "\n".join(lines)
