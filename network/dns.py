"""DNS Switcher (CleanBoost v2.5, A.3).

- Switch between preset DNS providers (Cloudflare / Google / Quad9)
  or back to automatic (ISP / DHCP) DNS.
- The previous DNS is ALWAYS saved to dns_backup.json BEFORE any
  change, so "Undo" restores exactly what was there.
- Measure each provider's resolve time on this PC (nslookup) and
  suggest the fastest one.
- Changing DNS needs Admin: every setter checks privilege.is_admin()
  first and reports clearly when it is missing.

Never raises — returns (ok, message[, data]).
"""
import json
import os
import subprocess
import sys
import time

from cleaner import action_log
from core import privilege

PRESETS = {
    "Cloudflare": ("1.1.1.1", "1.0.0.1"),
    "Google": ("8.8.8.8", "8.8.4.4"),
    "Quad9": ("9.9.9.9", "149.112.112.112"),
}

_IP_RE = None


def _ip_regex():
    global _IP_RE
    if _IP_RE is None:
        import re
        _IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    return _IP_RE


def _config_dir():
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "CleanBoost")
    else:
        d = os.path.join(os.path.expanduser("~"), ".config", "cleanboost")
    os.makedirs(d, exist_ok=True)
    return d


def _backup_path():
    return os.path.join(_config_dir(), "dns_backup.json")


def _run(argv, timeout=30):
    try:
        r = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, errors="replace")
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except FileNotFoundError:
        return -1, f"Command not found: {argv[0]}"
    except subprocess.TimeoutExpired:
        return -1, "Command timed out."
    except Exception as e:  # noqa: BLE001
        return -1, f"Command error: {e}"


def get_active_adapter():
    """Name of the primary (connected) adapter, or "" when unknown."""
    try:
        from network import info as net_info
        _ok, _msg, data = net_info.get_network_info()
        if data.get("adapter_name"):
            return data["adapter_name"]
    except Exception:
        pass
    try:
        import psutil
        stats = psutil.net_if_stats()
        for name, st in stats.items():
            if st.isup:
                return name
    except Exception:
        pass
    return ""


def get_current_dns(adapter=None):
    """Current DNS servers of one adapter.

    Returns (ok, message, {"adapter": name, "dns": [...]}).
    """
    try:
        adapter = adapter or get_active_adapter()
        dns = []
        if sys.platform == "win32" and adapter:
            _rc, out = _run(["netsh", "interface", "ip", "show", "dns", adapter])
            for m in _ip_regex().finditer(out):
                ip = m.group(0)
                if ip not in dns:
                    dns.append(ip)
        if not dns:
            from network import info as net_info
            _ok, _msg, data = net_info.get_network_info()
            dns = list(data.get("dns") or [])
        return True, f"DNS on {adapter or 'this PC'}: " + (
            ", ".join(dns) if dns else "automatic / unknown"), {
            "adapter": adapter, "dns": dns}
    except Exception as e:  # noqa: BLE001
        return False, f"Could not read current DNS: {e}", {"adapter": adapter or "", "dns": []}


def backup_info():
    """Saved DNS backup, or None when no backup exists."""
    try:
        with open(_backup_path(), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "dns" in data:
            return data
    except Exception:
        pass
    return None


def _save_backup(adapter, dns):
    try:
        with open(_backup_path(), "w", encoding="utf-8") as f:
            json.dump({"adapter": adapter, "dns": list(dns or []),
                       "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                      f, ensure_ascii=False, indent=1)
        return True
    except OSError:
        return False


def _apply_static(adapter, primary, secondary=None):
    rc, out = _run(["netsh", "interface", "ip", "set", "dns",
                    adapter, "static", primary])
    if rc != 0:
        return False, f"Could not set primary DNS: {out.strip()[:300]}"
    if secondary:
        rc2, out2 = _run(["netsh", "interface", "ip", "add", "dns",
                          adapter, secondary, "index=2"])
        if rc2 != 0:
            return False, (f"Primary DNS set, but secondary failed: "
                           f"{out2.strip()[:300]}")
    return True, "DNS applied."


def _apply_dhcp(adapter):
    rc, out = _run(["netsh", "interface", "ip", "set", "dns", adapter, "dhcp"])
    if rc != 0:
        return False, f"Could not set automatic DNS: {out.strip()[:300]}"
    return True, "DNS set to automatic (DHCP)."


def _require_admin():
    if not privilege.is_admin():
        return (False,
                "Admin rights required to change DNS. "
                "Close CleanBoost and run it as Administrator, then try again.")
    return None


def set_dns(primary, secondary=None, adapter=None):
    """Switch to a static DNS pair. Saves the old DNS first.

    Returns (ok, message).
    """
    try:
        denied = _require_admin()
        if denied:
            return denied
        if sys.platform != "win32":
            return False, "DNS switching is only supported on Windows."
        adapter = adapter or get_active_adapter()
        if not adapter:
            return False, "Could not find the active network adapter."
        _ok, _msg, cur = get_current_dns(adapter)
        # v2.5.6: the backup MUST succeed before any change — a failed
        # backup used to mean the old DNS was lost and Undo could not
        # restore it. Abort instead of changing DNS blindly.
        if not _save_backup(adapter, cur.get("dns") or []):
            return False, ("Could not save a backup of your current DNS — "
                           "aborting so Undo stays possible. Check disk "
                           "space / permissions and try again.")
        ok, msg = _apply_static(adapter, primary, secondary)
        action_log.log("network_dns_change",
                       {"adapter": adapter, "primary": primary,
                        "secondary": secondary, "ok": ok})
        if ok:
            return True, (f"DNS changed to {primary}"
                          + (f" / {secondary}" if secondary else "")
                          + f" on {adapter}. Previous DNS saved — "
                            "use Undo to restore it.")
        return False, msg
    except Exception as e:  # noqa: BLE001
        return False, f"Could not change DNS: {e}"


def set_dns_auto(adapter=None):
    """Switch back to automatic (ISP / DHCP) DNS. Saves the old DNS first."""
    try:
        denied = _require_admin()
        if denied:
            return denied
        if sys.platform != "win32":
            return False, "DNS switching is only supported on Windows."
        adapter = adapter or get_active_adapter()
        if not adapter:
            return False, "Could not find the active network adapter."
        _ok, _msg, cur = get_current_dns(adapter)
        # v2.5.6: same rule as set_dns — backup must succeed first.
        if not _save_backup(adapter, cur.get("dns") or []):
            return False, ("Could not save a backup of your current DNS — "
                           "aborting so Undo stays possible. Check disk "
                           "space / permissions and try again.")
        ok, msg = _apply_dhcp(adapter)
        action_log.log("network_dns_change",
                       {"adapter": adapter, "mode": "auto", "ok": ok})
        if ok:
            return True, (f"DNS set to automatic on {adapter}. "
                          "Previous DNS saved — use Undo to restore it.")
        return False, msg
    except Exception as e:  # noqa: BLE001
        return False, f"Could not change DNS: {e}"


def restore_dns(adapter=None):
    """Restore the DNS saved before the last change (Undo button)."""
    try:
        denied = _require_admin()
        if denied:
            return denied
        if sys.platform != "win32":
            return False, "DNS switching is only supported on Windows."
        backup = backup_info()
        if not backup:
            return False, ("No saved DNS backup found — nothing to undo. "
                           "Change DNS once and a backup will be created.")
        adapter = adapter or backup.get("adapter") or get_active_adapter()
        if not adapter:
            return False, "Could not find the network adapter to restore."
        dns = backup.get("dns") or []
        if dns:
            ok, msg = _apply_static(adapter, dns[0],
                                    dns[1] if len(dns) > 1 else None)
            what = ", ".join(dns)
        else:
            ok, msg = _apply_dhcp(adapter)
            what = "automatic (DHCP)"
        action_log.log("network_dns_restore",
                       {"adapter": adapter, "restored": dns, "ok": ok})
        if ok:
            return True, f"DNS restored to {what} on {adapter}."
        return False, msg
    except Exception as e:  # noqa: BLE001
        return False, f"Could not restore DNS: {e}"


def measure_dns(host="google.com", tries=2, servers=None):
    """Resolve time per DNS server (nslookup), fastest first.

    v2.5.6: 2 tries x 5s timeout (was 3 x 15s = up to 135s of
    "Measuring..." when a provider was unreachable). Times include
    nslookup startup, so compare servers relatively.
    Returns (ok, message, [{"name", "server", "avg_ms", "ok"}]).
    """
    try:
        servers = servers or PRESETS
        results = []
        for name, pair in servers.items():
            server = pair[0]
            times = []
            for _ in range(tries):
                start = time.time()
                rc, _out = _run(["nslookup", host, server], timeout=5)
                if rc == 0:
                    times.append((time.time() - start) * 1000.0)
            if times:
                results.append({"name": name, "server": server,
                                "avg_ms": sum(times) / len(times),
                                "ok": True})
            else:
                results.append({"name": name, "server": server,
                                "avg_ms": None, "ok": False})
        results.sort(key=lambda r: (r["avg_ms"] is None, r["avg_ms"] or 0))
        good = [r for r in results if r["ok"]]
        if not good:
            return False, "Could not measure any DNS server.", results
        best = good[0]
        return (True,
                f"Fastest DNS: {best['name']} ({best['server']}) — "
                f"{best['avg_ms']:.0f} ms.", results)
    except Exception as e:  # noqa: BLE001
        return False, f"Could not measure DNS speed: {e}", []
