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
    if sys.platform == "win32":
        argv = ["ping", "-n", "2", target]
    else:
        argv = ["ping", "-c", "2", target]
    ok, msg, _out = _run(argv, timeout=20)
    if ok:
        return True, f"Connection OK (ping {target} succeeded)."
    return False, f"Could not reach {target} after refresh: {msg}"


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
