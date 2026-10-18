"""Speed Test (CleanBoost v2.4, A.5) — ping, DNS time, download speed.

No third-party libraries: subprocess ping, nslookup (fallback:
socket.getaddrinfo timing), urllib download of a 10 MB test file.
Never raises — returns (ok, message, data).
"""
import re
import socket
import subprocess
import sys
import time
import urllib.request

DOWNLOAD_URL = "https://speed.cloudflare.com/__down?bytes=10000000"
DOWNLOAD_BYTES = 10_000_000


def ping_host(host, count=4, timeout=20):
    """Average ping to host in ms. (ok, message, ms_or_None)."""
    try:
        if sys.platform == "win32":
            argv = ["ping", "-n", str(count), host]
        else:
            argv = ["ping", "-c", str(count), host]
        r = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, errors="replace")
        out = r.stdout or ""
        if sys.platform == "win32":
            m = re.search(r"Average\s*=\s*([\d.]+)\s*ms", out)
            if m:
                return True, f"Ping {host}: {m.group(1)} ms.", float(m.group(1))
        else:
            m = re.search(r"=\s*[\d.]+/([\d.]+)/[\d.]+/[\d.]+\s*ms", out)
            if m:
                return True, f"Ping {host}: {m.group(1)} ms.", float(m.group(1))
        return False, f"Ping {host} failed.", None
    except FileNotFoundError:
        return False, "ping command not found.", None
    except Exception as e:  # noqa: BLE001
        return False, f"Ping {host} failed: {e}", None


def measure_dns_time(host="google.com", timeout=10):
    """Time to resolve host, in ms. (ok, message, ms_or_None)."""
    try:
        start = time.time()
        r = subprocess.run(["nslookup", host], capture_output=True,
                           text=True, timeout=timeout, errors="replace")
        elapsed_ms = (time.time() - start) * 1000.0
        if r.returncode == 0:
            return True, f"DNS resolve {host}: {elapsed_ms:.0f} ms.", elapsed_ms
        raise RuntimeError("nslookup failed")
    except Exception:
        # Fallback: time the resolver itself (no external tool needed).
        try:
            start = time.time()
            socket.getaddrinfo(host, 443)
            elapsed_ms = (time.time() - start) * 1000.0
            return True, f"DNS resolve {host}: {elapsed_ms:.0f} ms.", elapsed_ms
        except Exception as e:  # noqa: BLE001
            return False, f"DNS resolve failed: {e}", None


def download_speed(url=DOWNLOAD_URL, timeout=30):
    """Download speed in Mbps. (ok, message, mbps_or_None)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CleanBoost/2.4"})
        start = time.time()
        total = 0
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total >= DOWNLOAD_BYTES:
                    break
        elapsed = max(time.time() - start, 0.001)
        mbps = total * 8 / elapsed / 1_000_000
        return True, f"Download: {mbps:.1f} Mbps ({total / 1e6:.1f} MB).", mbps
    except Exception as e:  # noqa: BLE001
        return False, f"Download test failed: {e}", None


def run_speed_test(progress_cb=None):
    """Full test: ping 1.1.1.1, ping 8.8.8.8, DNS time, download speed.

    progress_cb(stage, done, total) is called before each of the 4 steps.
    Returns (ok, message, results dict). ok is True when at least one
    measurement succeeded; failed steps stay None with a note.
    """
    results = {"ping_1_1_1_1_ms": None, "ping_8_8_8_8_ms": None,
               "dns_ms": None, "download_mbps": None, "notes": []}
    steps = [
        ("ping_1_1_1_1_ms", lambda: ping_host("1.1.1.1")),
        ("ping_8_8_8_8_ms", lambda: ping_host("8.8.8.8")),
        ("dns_ms", lambda: measure_dns_time("google.com")),
        ("download_mbps", lambda: download_speed()),
    ]
    for i, (key, fn) in enumerate(steps):
        try:
            if progress_cb:
                progress_cb(key, i, len(steps))
            ok, msg, val = fn()
            results[key] = val
            if not ok:
                results["notes"].append(msg)
        except Exception as e:  # noqa: BLE001
            results["notes"].append(f"{key} failed: {e}")
    if progress_cb:
        progress_cb("done", len(steps), len(steps))
    if all(results[k] is None for k in
           ("ping_1_1_1_1_ms", "ping_8_8_8_8_ms", "dns_ms", "download_mbps")):
        return False, "Speed test failed: no measurement succeeded.", results
    parts = []
    if results["ping_1_1_1_1_ms"] is not None:
        parts.append(f"ping 1.1.1.1 {results['ping_1_1_1_1_ms']:.0f} ms")
    if results["ping_8_8_8_8_ms"] is not None:
        parts.append(f"ping 8.8.8.8 {results['ping_8_8_8_8_ms']:.0f} ms")
    if results["dns_ms"] is not None:
        parts.append(f"DNS {results['dns_ms']:.0f} ms")
    if results["download_mbps"] is not None:
        parts.append(f"download {results['download_mbps']:.1f} Mbps")
    msg = "Speed test: " + ", ".join(parts) + "."
    if results["notes"]:
        msg += " (" + "; ".join(results["notes"]) + ")"
    return True, msg, results


def format_speed(results):
    """One-line English summary of a results dict (None-safe)."""
    def fmt(v, unit):
        return f"{v:.0f} {unit}" if v is not None else "-"
    return ("Ping 1.1.1.1: " + fmt(results.get("ping_1_1_1_1_ms"), "ms")
            + " | Ping 8.8.8.8: " + fmt(results.get("ping_8_8_8_8_ms"), "ms")
            + " | DNS: " + fmt(results.get("dns_ms"), "ms")
            + " | Download: "
            + (f"{results['download_mbps']:.1f} Mbps"
               if results.get("download_mbps") is not None else "-"))
