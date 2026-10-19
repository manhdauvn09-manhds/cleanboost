"""Network Info Dashboard (CleanBoost v2.4, A.8).

Read-only: Local IP / Subnet / MAC, Global IP, Gateway, DNS, WiFi.
Never raises — every section degrades to "" / [] / None on failure.
Returns (ok, message, data).
"""
import ipaddress
import re
import socket
import subprocess
import urllib.request

import psutil

_GLOBAL_IP_URLS = (
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
)
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _run(argv, timeout=10):
    """Run a command, return stdout text ("" on any failure)."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, errors="replace")
        return r.stdout or ""
    except Exception:
        return ""


def _is_valid_ipv4(s):
    try:
        ipaddress.IPv4Address(s)
        return True
    except Exception:
        return False


def _adapters():
    """One dict per UP adapter with an IPv4 address."""
    out = []
    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
    except Exception:
        return out
    for name, lst in addrs.items():
        st = stats.get(name)
        if st is not None and not st.isup:
            continue
        row = {"name": name, "ipv4": "", "subnet": "", "mac": "", "ipv6": ""}
        for a in lst:
            fam = getattr(a, "family", None)
            # AF_INET == 2, AF_INET6 == 10, AF_PACKET == 17 (Linux),
            # AF_LINK == -1 (Windows psutil uses -1 for MAC).
            if fam == socket.AF_INET and a.address and not a.address.startswith("127."):
                if not row["ipv4"]:
                    row["ipv4"] = a.address
                    row["subnet"] = a.netmask or ""
            elif fam == socket.AF_INET6 and a.address and not a.address.startswith(("::1", "fe80")):
                if not row["ipv6"]:
                    row["ipv6"] = a.address.split("%")[0]
            elif fam in (psutil.AF_LINK, -1, 17) and a.address:
                if not row["mac"]:
                    row["mac"] = a.address
        if row["ipv4"] or row["mac"]:
            out.append(row)
    return out


def _pick_primary(adapters):
    """Primary adapter: first UP adapter with a real (non-link-local) IPv4."""
    for a in adapters:
        ip = a.get("ipv4", "")
        if ip and not ip.startswith("169.254."):
            return a
    for a in adapters:
        if a.get("ipv4"):
            return a
    return adapters[0] if adapters else {}


def _global_ip():
    """Public IP via ipify (fallback ifconfig.me). "" when offline.

    v2.5.5: 3s per URL (was 5s) — the Network tab's "Loading..."
    waited up to 10s on a slow/blocked connection before showing
    anything. A missing Global IP just shows "-" and the rest loads.
    """
    for url in _GLOBAL_IP_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CleanBoost/2.4"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                txt = resp.read().decode("utf-8", "replace").strip()
            if _is_valid_ipv4(txt):
                return txt, url
        except Exception:
            continue
    return "", ""


def _gateway_from_route_print(out):
    # "0.0.0.0  0.0.0.0  192.168.1.1  ..." — Gateway is the 3rd column.
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
            if _is_valid_ipv4(parts[2]):
                return parts[2]
    return ""


def _gateway_from_ipconfig(out):
    # "Default Gateway . . . . . . . . . : 192.168.1.1"
    for line in out.splitlines():
        if "gateway" in line.lower() and ":" in line:
            m = _IP_RE.search(line.split(":", 1)[1])
            if m and _is_valid_ipv4(m.group(0)):
                return m.group(0)
    return ""


def _gateway():
    import sys
    if sys.platform == "win32":
        gw = _gateway_from_route_print(_run(["route", "print", "-4"]))
        if gw:
            return gw
        return _gateway_from_ipconfig(_run(["ipconfig"]))
    # Linux fallback (dev machine / tests): "default via 192.168.1.1 ..."
    out = _run(["ip", "route", "show", "default"])
    m = re.search(r"default via\s+(\S+)", out)
    if m and _is_valid_ipv4(m.group(1)):
        return m.group(1)
    return ""


def _dns_from_ipconfig(out):
    # "DNS Servers . . . . . . . . . . . : 1.1.1.1" (+ continuation lines)
    dns, capture = [], False
    for line in out.splitlines():
        low = line.lower()
        if "dns servers" in low and ":" in line:
            capture = True
            m = _IP_RE.search(line.split(":", 1)[1])
            if m and _is_valid_ipv4(m.group(0)):
                dns.append(m.group(0))
            continue
        if capture:
            s = line.strip()
            if not s:
                break
            m = _IP_RE.match(s)
            if m and _is_valid_ipv4(m.group(0)):
                dns.append(m.group(0))
                continue
            break
    return dns


def _dns():
    import sys
    if sys.platform == "win32":
        dns = _dns_from_ipconfig(_run(["ipconfig", "/all"]))
        if dns:
            return dns
        # Fallback: "netsh interface ip show dns" lists "DNS Servers: 1.1.1.1"
        out = _run(["netsh", "interface", "ip", "show", "dns"])
        found = []
        for m in _IP_RE.finditer(out):
            if _is_valid_ipv4(m.group(0)) and m.group(0) not in found:
                found.append(m.group(0))
        return found
    # Linux fallback: /etc/resolv.conf
    try:
        found = []
        with open("/etc/resolv.conf", encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "nameserver":
                    if _is_valid_ipv4(parts[1]) and parts[1] not in found:
                        found.append(parts[1])
        return found
    except OSError:
        return []


def _wifi():
    """WiFi info from 'netsh wlan show interfaces'. None on LAN / failure."""
    import sys
    if sys.platform != "win32":
        return None
    out = _run(["netsh", "wlan", "show", "interfaces"])
    if not out or "SSID" not in out:
        return None
    wifi = {"ssid": "", "signal_percent": None, "receive_rate_mbps": "",
            "transmit_rate_mbps": "", "channel": "", "auth": ""}
    for line in out.splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key, val = key.strip().lower(), val.strip()
        if key == "ssid" and not wifi["ssid"]:
            wifi["ssid"] = val
        elif key == "signal" and "%" in val:
            try:
                wifi["signal_percent"] = int(val.replace("%", "").strip())
            except ValueError:
                pass
        elif key == "receive rate (mbps)":
            wifi["receive_rate_mbps"] = val
        elif key == "transmit rate (mbps)":
            wifi["transmit_rate_mbps"] = val
        elif key == "channel":
            wifi["channel"] = val
        elif key == "authentication":
            wifi["auth"] = val
    if not wifi["ssid"]:
        return None
    return wifi


def get_network_info():
    """Collect the Network Info Dashboard data.

    Returns (ok, message, data). ok is False only when no adapter
    could be found at all; individual missing fields stay empty.
    """
    try:
        adapters = _adapters()
        if not adapters:
            return False, "No network adapters found.", {"adapters": []}
        primary = _pick_primary(adapters)
        global_ip, global_src = _global_ip()
        data = {
            "adapters": adapters,
            "local_ip": primary.get("ipv4", ""),
            "subnet": primary.get("subnet", ""),
            "mac": primary.get("mac", ""),
            "ipv6": primary.get("ipv6", ""),
            "adapter_name": primary.get("name", ""),
            "global_ip": global_ip,
            "global_ip_source": global_src,
            "gateway": _gateway(),
            "dns": _dns(),
            "wifi": _wifi(),
            "hostname": socket.gethostname(),
        }
        missing = [k for k in ("local_ip", "gateway")
                   if not data[k]]
        if global_ip == "":
            missing.append("global_ip")
        if missing:
            return (True,
                    "Network info collected (unavailable: "
                    + ", ".join(missing) + ").", data)
        return True, "Network info collected.", data
    except Exception as e:  # noqa: BLE001 — never raise
        return False, f"Could not collect network info: {e}", {"adapters": []}


def format_info(data):
    """One English plain-text block for the UI textbox / dialogs."""
    lines = [f"Hostname: {data.get('hostname', '')}"]
    lines.append(f"Adapter: {data.get('adapter_name', '')}")
    lines.append(f"Local IP: {data.get('local_ip', '') or '-'}")
    lines.append(f"Subnet mask: {data.get('subnet', '') or '-'}")
    lines.append(f"MAC: {data.get('mac', '') or '-'}")
    if data.get("ipv6"):
        lines.append(f"IPv6: {data['ipv6']}")
    lines.append(f"Global IP: {data.get('global_ip', '') or '-'}")
    lines.append(f"Gateway: {data.get('gateway', '') or '-'}")
    dns = data.get("dns") or []
    lines.append("DNS: " + (", ".join(dns) if dns else "-"))
    wifi = data.get("wifi")
    if wifi:
        sig = wifi.get("signal_percent")
        lines.append(f"WiFi SSID: {wifi.get('ssid', '')}")
        lines.append("WiFi signal: "
                     + (f"{sig}%" if sig is not None else "-"))
        lines.append(f"WiFi link: {wifi.get('receive_rate_mbps', '') or '-'} "
                     f"Mbps RX / {wifi.get('transmit_rate_mbps', '') or '-'} "
                     "Mbps TX")
        if wifi.get("channel"):
            lines.append(f"WiFi channel: {wifi['channel']}")
    else:
        lines.append("WiFi: - (wired connection or no WiFi)")
    return "\n".join(lines)
