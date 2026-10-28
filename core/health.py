"""Health Score 0-100 (CleanBoost v2.4, B.2).

Transparent formula (ke-hoach-v3, section 2, B.2):

    score = 100
      - (100 - %RAM free) x 0.3
      - (100 - %disk free) x 0.3
      - min(junk / 5 GB, 1) x 20
      - min(startup apps / 20, 1) x 10
      - min(days since last clean / 30, 1) x 10

compute_health() never scans the disk itself: the caller passes
junk_bytes (from a level-1 scan) or leaves it None, in which case the
junk penalty is 0 and the result says junk was not measured.
Startup count is a read-only registry count (no enable/disable here);
days since last clean comes from the action_log "clean" entries.
Never raises — returns (ok, message, data).
"""
import json
import sys
from datetime import datetime, timezone

from cleaner import action_log
from core import system_info

GB = 1024 ** 3
JUNK_FULL_GB = 5.0
STARTUP_FULL = 20
AGE_FULL_DAYS = 30


def _count_startup():
    """Read-only count of Run-key startup entries (Windows). 0 elsewhere."""
    if sys.platform != "win32":
        return 0
    try:
        import winreg
        count = 0
        for hive, sub in (
                (winreg.HKEY_CURRENT_USER,
                 r"Software\Microsoft\Windows\CurrentVersion\Run"),
                (winreg.HKEY_LOCAL_MACHINE,
                 r"Software\Microsoft\Windows\CurrentVersion\Run")):
            try:
                with winreg.OpenKey(hive, sub) as key:
                    count += winreg.QueryInfoKey(key)[1]
            except OSError:
                continue
        return count
    except Exception:
        return 0


def _days_since_last_clean():
    """Days since the last 'clean' action_log entry. None if never."""
    try:
        path = action_log.path()
        last = None
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if entry.get("action") != "clean":
                    continue
                try:
                    ts = datetime.fromisoformat(entry.get("ts", ""))
                except ValueError:
                    continue
                if last is None or ts > last:
                    last = ts
        if last is None:
            return None
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - last
        return max(0, delta.days)
    except OSError:
        return None
    except Exception:
        return None


def compute_health(junk_bytes=None, startup_count=None,
                   last_clean_days=None, ram_free_pct=None,
                   disk_free_pct=None):
    """Compute the Health Score. Returns (ok, message, data)."""
    try:
        if ram_free_pct is None:
            mem = system_info.memory()
            ram_free_pct = 100.0 - mem["percent"]
        if disk_free_pct is None:
            root = "C:\\" if sys.platform == "win32" else "/"
            disk = system_info.disk(root)
            disk_free_pct = 100.0 - disk["percent"]
        if startup_count is None:
            startup_count = _count_startup()
        if last_clean_days is None:
            last_clean_days = _days_since_last_clean()

        ram_penalty = (100.0 - ram_free_pct) * 0.3
        disk_penalty = (100.0 - disk_free_pct) * 0.3
        if junk_bytes is None:
            junk_penalty = 0.0
            junk_measured = False
        else:
            junk_penalty = min(max(junk_bytes, 0) / (JUNK_FULL_GB * GB), 1.0) * 20
            junk_measured = True
        startup_penalty = min(max(startup_count, 0) / STARTUP_FULL, 1.0) * 10
        if last_clean_days is None:
            age_penalty = 0.0
        else:
            age_penalty = min(max(last_clean_days, 0) / AGE_FULL_DAYS, 1.0) * 10

        score = 100.0 - (ram_penalty + disk_penalty + junk_penalty
                         + startup_penalty + age_penalty)
        score = int(round(max(0, min(100, score))))

        suggestions = []
        if ram_free_pct < 30:
            suggestions.append(
                "RAM is low — run Light RAM clean or close heavy apps.")
        if disk_free_pct < 15:
            suggestions.append(
                "Disk is nearly full — clean junk files to free space.")
        if junk_measured and (junk_bytes or 0) >= 500 * 1024 * 1024:
            gain = min((junk_bytes or 0) / (JUNK_FULL_GB * GB), 1.0) * 20
            suggestions.append(
                f"Clean {junk_bytes / GB:.1f} GB of junk to gain up to "
                f"{gain:.0f} points.")
        elif not junk_measured:
            suggestions.append(
                "Junk not measured yet — run a Disk Cleaner scan to include "
                "it in the score.")
        if startup_count >= 10:
            suggestions.append(
                f"{startup_count} apps start with Windows — disable the "
                "ones you do not need to boot faster.")
        if last_clean_days is not None and last_clean_days >= 14:
            suggestions.append(
                f"Last cleanup was {last_clean_days} days ago — run "
                "Optimize in 1 Click.")
        if not suggestions:
            suggestions.append("Your PC looks healthy — nice work.")

        data = {
            "score": score,
            "ram_free_pct": round(ram_free_pct, 1),
            "disk_free_pct": round(disk_free_pct, 1),
            "junk_bytes": junk_bytes,
            "junk_measured": junk_measured,
            "startup_count": int(startup_count),
            "days_since_clean": last_clean_days,
            "penalties": {
                "ram": round(ram_penalty, 1),
                "disk": round(disk_penalty, 1),
                "junk": round(junk_penalty, 1),
                "startup": round(startup_penalty, 1),
                "age": round(age_penalty, 1),
            },
            "suggestions": suggestions,
        }
        return True, f"Health Score: {score}/100.", data
    except Exception as e:  # noqa: BLE001 — never raise
        return False, f"Could not compute Health Score: {e}", {"score": 0}


def format_health(data):
    """Short English breakdown for the UI."""
    p = data.get("penalties", {})
    junk = data.get("junk_bytes")
    junk_s = f"{junk / GB:.1f} GB" if junk is not None else "not measured"
    days = data.get("days_since_clean")
    days_s = f"{days} day(s)" if days is not None else "never"
    return (f"RAM free {data.get('ram_free_pct')}% (-{p.get('ram', 0)}) | "
            f"Disk free {data.get('disk_free_pct')}% (-{p.get('disk', 0)}) | "
            f"Junk {junk_s} (-{p.get('junk', 0)}) | "
            f"Startup {data.get('startup_count')} apps (-{p.get('startup', 0)}) | "
            f"Last clean {days_s} (-{p.get('age', 0)})")
