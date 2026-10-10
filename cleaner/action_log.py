"""Audit log: every kill/clean/restore action is recorded here (JSONL)."""
import json
import os
import sys
from datetime import datetime, timezone


def _path() -> str:
    if sys.platform == "win32":
        base = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        base = os.path.join(base, "CleanBoost")
    else:
        base = os.path.join(os.path.expanduser("~"), ".local", "share", "cleanboost")
    return os.path.join(base, "actions.jsonl")


def log(action: str, detail: dict):
    """Write one log line. Never raises (log errors are ignored)."""
    try:
        os.makedirs(os.path.dirname(_path()), exist_ok=True)
        entry = {"ts": datetime.now(timezone.utc).isoformat(),
                 "action": action, "detail": detail}
        with open(_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def path() -> str:
    return _path()
