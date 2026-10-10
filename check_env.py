#!/usr/bin/env python3
"""Self-healing environment check.

Run with the venv's python (or any python). If requirements.txt changed
since the last install, reinstalls dependencies automatically.

This is what makes `git pull` + double-click work without re-running
setup_windows.bat: the launchers call this script on every start.

Exit code: 0 = environment OK, 1 = install failed.
"""
import hashlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REQ = os.path.join(ROOT, "requirements.txt")
HASH_FILE = os.path.join(ROOT, ".venv", "req.sha256")


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    if not os.path.exists(REQ):
        return 0
    current = _sha(REQ)
    try:
        with open(HASH_FILE, encoding="utf-8") as f:
            installed = f.read().strip()
    except OSError:
        installed = ""
    if current == installed:
        return 0  # nothing changed
    print("[CleanBoost] requirements.txt changed - installing dependencies...")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", REQ])
    if r.returncode != 0:
        print("[CleanBoost] ERROR: failed to install dependencies. "
              "Check your internet connection and run setup_windows.bat.")
        return 1
    try:
        os.makedirs(os.path.dirname(HASH_FILE), exist_ok=True)
        with open(HASH_FILE, "w", encoding="utf-8") as f:
            f.write(current)
    except OSError:
        pass
    print("[CleanBoost] Dependencies are up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
