"""Quarantine.

Cleaned files are MOVED here instead of deleted: kept 14 days,
1-click restore to the original location. Expired items are deleted
permanently (with confirmation).
"""
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone

RETENTION_DAYS = 14


def root() -> str:
    if sys.platform == "win32":
        base = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return os.path.join(base, "CleanBoost", "Quarantine")
    return os.path.join(os.path.expanduser("~"), ".local", "share",
                        "cleanboost", "quarantine")


def _index_path() -> str:
    return os.path.join(root(), "index.json")


def _load() -> dict:
    try:
        with open(_index_path(), encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {"items": []}
    except Exception:
        return {"items": []}


def _safe_stored(stored_rel: str):
    """Return the absolute path inside quarantine, or None on traversal."""
    base = os.path.realpath(root())
    abs_p = os.path.realpath(os.path.join(base, stored_rel))
    if abs_p == base or abs_p.startswith(base + os.sep):
        return abs_p
    return None


def _save(idx: dict):
    os.makedirs(root(), exist_ok=True)
    tmp = _index_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _index_path())


def _path_size(p: str) -> int:
    if os.path.isfile(p):
        try:
            return os.path.getsize(p)
        except OSError:
            return 0
    total = 0
    for dirpath, _d, files in os.walk(p, onerror=lambda e: None):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, fn))
            except OSError:
                continue
    return total


def put(orig_path: str, rule_id: str = "") -> dict:
    """Move one file or folder into quarantine. Returns the stored item."""
    os.makedirs(root(), exist_ok=True)
    batch = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    item_id = uuid.uuid4().hex[:12]
    stored_rel = os.path.join(batch, f"{item_id}_{os.path.basename(orig_path)}")
    stored_abs = os.path.join(root(), stored_rel)
    os.makedirs(os.path.dirname(stored_abs), exist_ok=True)
    size = _path_size(orig_path)
    shutil.move(orig_path, stored_abs)
    idx = _load()
    item = {
        "id": item_id,
        "orig": orig_path,
        "stored": stored_rel,
        "size": size,
        "rule": rule_id,
        "quarantined_at": datetime.now(timezone.utc).isoformat(),
    }
    idx["items"].append(item)
    _save(idx)
    return item


def list_items() -> list:
    return _load().get("items", [])


def total_size() -> int:
    return sum(i.get("size", 0) for i in list_items())


def restore(item_id: str):
    """Restore a file to its original location. Returns (ok, message)."""
    idx = _load()
    item = next((i for i in idx["items"] if i["id"] == item_id), None)
    if not item:
        return False, "Not found in quarantine."
    stored_abs = _safe_stored(item["stored"])
    if not stored_abs or not os.path.exists(stored_abs):
        return False, "Quarantined file no longer exists (may have been deleted manually)."
    os.makedirs(os.path.dirname(item["orig"]), exist_ok=True)
    dest = item["orig"]
    if os.path.exists(dest):
        # original location has a new file -> do not overwrite, rename
        dest = f"{dest}.restored_{item['id']}"
    shutil.move(stored_abs, dest)
    idx["items"] = [i for i in idx["items"] if i["id"] != item_id]
    _save(idx)
    return True, f"Restored to: {dest}"


def delete_permanent(item_id: str):
    """Permanently delete one quarantined item."""
    idx = _load()
    item = next((i for i in idx["items"] if i["id"] == item_id), None)
    if not item:
        return False, "Not found in quarantine."
    stored_abs = _safe_stored(item["stored"])
    if not stored_abs:
        return False, "Invalid path."
    try:
        if os.path.isdir(stored_abs) and not os.path.islink(stored_abs):
            shutil.rmtree(stored_abs, ignore_errors=False)
        elif os.path.lexists(stored_abs):
            os.remove(stored_abs)
    except OSError as e:
        return False, f"Could not delete: {e}"
    idx["items"] = [i for i in idx["items"] if i["id"] != item_id]
    _save(idx)
    return True, f"Permanently deleted: {os.path.basename(item['orig'])}"


def purge_expired(days: int = RETENTION_DAYS):
    """Permanently delete expired items. Returns (count, freed_bytes)."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    idx = _load()
    kept, removed, freed = [], 0, 0
    for item in idx["items"]:
        try:
            when = datetime.fromisoformat(item["quarantined_at"])
        except Exception:
            kept.append(item)
            continue
        if when < cutoff:
            stored_abs = _safe_stored(item["stored"])
            if not stored_abs:
                kept.append(item)
                continue
            try:
                if os.path.isdir(stored_abs) and not os.path.islink(stored_abs):
                    shutil.rmtree(stored_abs, ignore_errors=False)
                elif os.path.lexists(stored_abs):
                    os.remove(stored_abs)
                freed += item.get("size", 0)
                removed += 1
            except OSError:
                kept.append(item)  # delete failed -> keep
        else:
            kept.append(item)
    idx["items"] = kept
    _save(idx)
    return removed, freed
