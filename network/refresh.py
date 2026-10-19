"""Quick Refresh (CleanBoost v2.4, A.1).

Runs: ipconfig /flushdns -> /release -> /renew, then verifies the
connection with a ping. No admin gate (flushdns/release/renew report
their own errors). Every step is logged to action_log.
Never raises — returns (ok, message, steps).
"""
import subprocess
import sys

from cleaner import action_log


def _run(argv, timeout=60):
    """Run one command. Returns (ok, message, stdout)."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 0:
            return True, "OK", out
        return False, f"Command failed (exit {r.returncode}): {out.strip()[:300]}", out
    except FileNotFoundError:
        return False, f"Command not found: {argv[0]}", ""
    except subprocess.TimeoutExpired:
        return False, f"Command timed out: {' '.join(argv)}", ""
    except Exception as e:  # noqa: BLE001
        return False, f"Command error: {e}", ""


def _ping_once(host, timeout=10):
    """One ping (ping -n/-c 1). True when the host replies."""
    if sys.platform == "win32":
        argv = ["ping", "-n", "1", host]
    else:
        argv = ["ping", "-c", "1", host]
    ok, _msg, _out = _run(argv, timeout=timeout)
    return ok


def _verify():
    """Ping the gateway (fallback 1.1.1.1). Returns (ok, message)."""
    target = "1.1.1.1"
    try:
        from network import info as net_info
        _ok, _msg, data = net_info.get_network_info()
        if data.get("gateway"):
            target = data["gateway"]
    except Exception:
        pass
    if _ping_once(target, timeout=20):
        return True, f"Connection OK (ping {target} succeeded)."
    return False, f"Could not reach {target} after refresh."


def quick_refresh(progress_cb=None):
    """Run flushdns -> release -> renew -> verify.

    progress_cb(step_index, total, label) is called before each step.
    Returns (ok, message, steps) with steps = [{step, ok, message}].
    ok is True only when flushdns, release and renew all succeeded;
    a failed verify is reported as a warning, not a failure.
    """
    if sys.platform != "win32":
        steps = [{"step": "flushdns", "ok": False,
                  "message": "Quick Refresh requires Windows (ipconfig)."}]
        return False, "Quick Refresh requires Windows (ipconfig).", steps
    plan = [
        ("flushdns", ["ipconfig", "/flushdns"], 30),
        ("release", ["ipconfig", "/release"], 60),
        ("renew", ["ipconfig", "/renew"], 60),
    ]
    steps = []
    all_ok = True
    for i, (name, argv, timeout) in enumerate(plan):
        try:
            if progress_cb:
                progress_cb(i, len(plan) + 1, name)
            ok, msg, _out = _run(argv, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            ok, msg = False, f"Unexpected error: {e}"
        steps.append({"step": name, "ok": ok, "message": msg})
        action_log.log("network_quick_refresh_step",
                       {"step": name, "ok": ok, "message": msg})
        if not ok:
            all_ok = False
    try:
        if progress_cb:
            progress_cb(len(plan), len(plan) + 1, "verify")
        vok, vmsg = _verify()
    except Exception as e:  # noqa: BLE001
        vok, vmsg = False, f"Verify error: {e}"
    steps.append({"step": "verify", "ok": vok, "message": vmsg})
    action_log.log("network_quick_refresh",
                   {"ok": all_ok, "verify_ok": vok,
                    "steps": [{s["step"]: s["ok"]} for s in steps]})
    if not all_ok:
        failed = ", ".join(s["step"] for s in steps[:3] if not s["ok"])
        return False, f"Quick Refresh failed at: {failed}.", steps
    if not vok:
        return True, f"Quick Refresh done, but verify failed: {vmsg}", steps
    return True, "Quick Refresh done — DNS flushed, new IP obtained.", steps


def flush_network(progress_cb=None):
    """Flush stale network caches WITHOUT disconnecting (v2.6.0).

    Quick Refresh reconnects (release + renew). Flush Network instead
    cleans the caches that make sites fail or load slowly, and keeps
    your current IP:
      1. flushdns — empty the DNS resolver cache (no Admin needed)
      2. nbtstat -R — purge the NetBIOS name cache (Admin)
      3. arp -d * — clear the ARP cache, i.e. forget stale
         IP -> MAC mappings (Admin)
      4. netsh interface ip delete arpcache — clear the interface
         ARP cache (Admin)
      5. verify — ping the gateway to confirm the network still works

    Admin-only steps are SKIPPED with a clear note when the app does
    not run as Administrator — the rest still runs. ok is True when
    every runnable step succeeded.
    Returns (ok, message, steps) with steps =
    [{step, ok, message, skipped}].
    """
    if sys.platform != "win32":
        steps = [{"step": "flushdns", "ok": False,
                  "message": "Flush Network requires Windows.",
                  "skipped": False}]
        return False, "Flush Network requires Windows.", steps
    admin = _is_admin()
    plan = [
        ("flushdns", ["ipconfig", "/flushdns"], False),
        ("netbios", ["nbtstat", "-R"], True),
        ("arp", ["arp", "-d", "*"], True),
        ("arpcache", ["netsh", "interface", "ip", "delete", "arpcache"], True),
    ]
    steps = []
    all_ok = True
    skipped_any = False
    for i, (name, argv, needs_admin) in enumerate(plan):
        if progress_cb:
            progress_cb(i, len(plan) + 1, name)
        if needs_admin and not admin:
            steps.append({"step": name, "ok": True, "skipped": True,
                          "message": "Skipped — run as Administrator."})
            skipped_any = True
            continue
        try:
            ok, msg, _out = _run(argv, timeout=30)
        except Exception as e:  # noqa: BLE001
            ok, msg = False, f"Unexpected error: {e}"
        steps.append({"step": name, "ok": ok, "message": msg,
                      "skipped": False})
        action_log.log("network_flush_step",
                       {"step": name, "ok": ok, "message": msg})
        if not ok:
            all_ok = False
    try:
        if progress_cb:
            progress_cb(len(plan), len(plan) + 1, "verify")
        vok, vmsg = _verify()
    except Exception as e:  # noqa: BLE001
        vok, vmsg = False, f"Verify error: {e}"
    steps.append({"step": "verify", "ok": vok, "message": vmsg,
                  "skipped": False})
    action_log.log("network_flush",
                   {"ok": all_ok, "verify_ok": vok, "admin": admin})
    if not all_ok:
        failed = ", ".join(s["step"] for s in steps
                           if not s["ok"] and not s["skipped"])
        return False, f"Flush Network failed at: {failed}.", steps
    if not vok:
        return True, f"Flush Network done, but verify failed: {vmsg}", steps
    msg = "Flush Network done — stale caches cleared, connection kept."
    if skipped_any:
        msg += (" (Some steps skipped — run as Administrator for a full "
                "flush.)")
    return True, msg, steps


def _powershell(command):
    """Run one PowerShell command. Returns (ok, message, stdout)."""
    return _run(["powershell", "-NoProfile", "-NonInteractive",
                 "-Command", command], timeout=60)


def adapter_reset(adapter=None, cancel_event=None, progress_cb=None):
    """Disable + re-enable one network adapter (v2.5, A.2).

    The UI owns the 3-second countdown + Cancel button; this function
    checks cancel_event once right before disabling (abort if set) and
    then performs the reset. Needs Admin. Network drops for ~5-10s.
    Verifies the adapter comes back within ~30s.

    Returns (ok, message, steps).
    """
    steps = []
    try:
        if sys.platform != "win32":
            return False, "Adapter Reset requires Windows.", steps
        if not _is_admin():
            return (False,
                    "Admin rights required for Adapter Reset. "
                    "Run CleanBoost as Administrator.", steps)
        if adapter is None:
            try:
                from network import info as net_info
                _ok, _msg, data = net_info.get_network_info()
                adapter = data.get("adapter_name", "")
            except Exception:
                adapter = ""
        if not adapter or '"' in adapter:
            return False, "Could not find a valid network adapter.", steps
        if cancel_event is not None and cancel_event.is_set():
            return False, "Adapter Reset cancelled.", steps
        # v2.5.6: capture the gateway BEFORE disabling — the old verify
        # loop re-ran the full get_network_info() (incl. up to 6s of
        # Global-IP lookup) on every iteration, so "verify within ~30s"
        # really took up to ~130s.
        try:
            from network import info as net_info
            _ok, _msg, _data = net_info.get_network_info()
            gateway = _data.get("gateway", "") or "1.1.1.1"
        except Exception:
            gateway = "1.1.1.1"

        plan = [
            ("disable", f'Disable-NetAdapter -Name "{adapter}" -Confirm:$false'),
            ("wait", None),
            ("enable", f'Enable-NetAdapter -Name "{adapter}" -Confirm:$false'),
        ]
        for i, (name, cmd) in enumerate(plan):
            if progress_cb:
                progress_cb(i, len(plan) + 1, name)
            if name == "wait":
                import time as _time
                _time.sleep(3)
                steps.append({"step": "wait", "ok": True,
                              "message": "Waited 3 seconds."})
                continue
            ok, msg, _out = _powershell(cmd)
            steps.append({"step": name, "ok": ok, "message": msg})
            action_log.log("network_adapter_reset_step",
                           {"step": name, "adapter": adapter, "ok": ok})
            if not ok:
                return False, f"Adapter Reset failed at {name}: {msg}", steps

        # Verify: adapter back UP + gateway reachable, up to ~30s.
        # Lightweight per iteration: psutil isup check + 1 ping.
        if progress_cb:
            progress_cb(len(plan), len(plan) + 1, "verify")
        import time as _time
        verified = False
        for _ in range(10):
            try:
                import psutil
                stats = psutil.net_if_stats()
                up = stats.get(adapter).isup if stats.get(adapter) else False
            except Exception:
                up = False
            if up and _ping_once(gateway, timeout=5):
                verified = True
                break
            _time.sleep(3)
        steps.append({"step": "verify", "ok": verified,
                      "message": "Adapter is back and reachable."
                      if verified else "Adapter did not come back within 30s."})
        action_log.log("network_adapter_reset",
                       {"adapter": adapter, "ok": verified})
        if verified:
            return True, f"Adapter '{adapter}' reset — connection restored.", steps
        return (False, "Adapter was reset but the connection did not come "
                "back within 30s. Check WiFi / cable.", steps)
    except Exception as e:  # noqa: BLE001
        return False, f"Adapter Reset failed: {e}", steps


def deep_reset():
    """Reset Winsock + TCP/IP stack (v2.5, A.4).

    Needs Admin. The UI shows a red warning + "I understand" checkbox
    before calling this. A RESTART is required afterwards.
    Returns (ok, message, steps).
    """
    steps = []
    try:
        if sys.platform != "win32":
            return False, "Deep Reset requires Windows.", steps
        if not _is_admin():
            return (False,
                    "Admin rights required for Deep Reset. "
                    "Run CleanBoost as Administrator.", steps)
        for name, argv in (("winsock", ["netsh", "winsock", "reset"]),
                           ("tcpip", ["netsh", "int", "ip", "reset"])):
            ok, msg, _out = _run(argv, timeout=60)
            steps.append({"step": name, "ok": ok, "message": msg})
            action_log.log("network_deep_reset_step",
                           {"step": name, "ok": ok})
            if not ok:
                return False, f"Deep Reset failed at {name}: {msg}", steps
        action_log.log("network_deep_reset", {"ok": True})
        return (True,
                "Deep Reset done — RESTART your PC now for it to take effect.",
                steps)
    except Exception as e:  # noqa: BLE001
        return False, f"Deep Reset failed: {e}", steps


def _is_admin():
    try:
        from core import privilege
        return privilege.is_admin()
    except Exception:
        return False
