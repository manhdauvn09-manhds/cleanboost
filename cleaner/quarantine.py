"""Quarantine.

Cleaned files are MOVED here instead of deleted: kept 14 days,
1-click restore to the original location. Expired items are deleted
permanently (with confirmation).
"""
import json
import os
import shutil
import stat
import sys
import uuid
from datetime import datetime, timezone
from cleaner.fs_walk import safe_walk

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


def _on_rm_error(func, path, _exc_info):
    """shutil.rmtree error handler: clear read-only, retry once.

    On Windows, rmtree fails on read-only files (PermissionError) — and
    quarantined junk often contains read-only files. Without this,
    Delete permanently silently fails on exactly those items.
    """
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _remove_path(path):
    """Permanently remove a file, symlink or directory tree.

    Returns (ok, message). Never raises. Missing path counts as
    removed (nothing left on disk). Read-only files are chmodded and
    retried; locked/in-use files report the real OS error instead of
    failing silently.
    """
    try:
        if not os.path.lexists(path):
            return True, "Already gone."
        if os.path.isdir(path) and not os.path.islink(path):
            try:
                shutil.rmtree(path, onerror=_on_rm_error)
            except OSError as e:
                return False, f"Could not delete folder: {e}"
            return True, "Folder deleted."
        try:
            os.remove(path)
        except PermissionError:
            try:
                os.chmod(path, stat.S_IWRITE)
                os.remove(path)
            except OSError as e:
                return False, f"Could not delete file: {e}"
        except OSError as e:
            return False, f"Could not delete file: {e}"
        return True, "File deleted."
    except Exception as e:  # noqa: BLE001
        return False, f"Could not delete: {e}"


# Public alias: clean.py uses it for orphan folders.
remove_path = _remove_path


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
    for dirpath, _d, files in safe_walk(p):
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


def prune_stale() -> int:
    """Drop index entries whose stored file no longer exists (v2.5.3).

    Stored files can vanish outside the app (user deleted them by hand,
    another cleaner, a failed restore). Those entries clog the table
    forever — they are not real files anymore, so remove them from the
    list. Entries with an invalid stored path are dropped too (we would
    refuse to touch them anyway). Returns how many were removed.
    Never raises.
    """
    try:
        idx = _load()
        items = idx.get("items", [])
        kept = []
        for item in items:
            stored_abs = _safe_stored(item.get("stored", ""))
            if stored_abs and os.path.lexists(stored_abs):
                kept.append(item)
        removed = len(items) - len(kept)
        if removed:
            idx["items"] = kept
            _save(idx)
        return removed
    except Exception:  # noqa: BLE001
        return 0


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
        return False, "Invalid path — refusing to delete outside quarantine."
    ok, msg = _remove_path(stored_abs)
    if not ok:
        return False, msg
    idx["items"] = [i for i in idx["items"] if i["id"] != item_id]
    _save(idx)
    return True, f"Permanently deleted: {os.path.basename(item['orig'])}"


def delete_all(progress_cb=None):
    """Permanently delete EVERYTHING in quarantine (Destroy All).

    Returns (ok, message, summary) with summary =
    {"deleted": int, "failed": [(id, name, reason)], "freed": bytes}.
    Failed items stay in the index with their real error reported —
    they are never silently kept. Never raises.
    progress_cb(done, total) is called after each item (for the UI
    progress bar); a failing callback never breaks the delete.
    """
    try:
        idx = _load()
        items = list(idx.get("items", []))
        kept, failed, deleted, freed = [], [], 0, 0
        for pos, item in enumerate(items, start=1):
            stored_abs = _safe_stored(item.get("stored", ""))
            if not stored_abs:
                kept.append(item)
                failed.append((item.get("id", "?"),
                               os.path.basename(item.get("orig", "?")),
                               "Invalid path — refusing to delete outside quarantine."))
            else:
                ok, msg = _remove_path(stored_abs)
                if ok:
                    deleted += 1
                    freed += item.get("size", 0)
                else:
                    kept.append(item)
                    failed.append((item.get("id", "?"),
                                   os.path.basename(item.get("orig", "?")), msg))
            if progress_cb is not None:
                try:
                    progress_cb(pos, len(items))
                except Exception:  # noqa: BLE001
                    pass
        idx["items"] = kept
        _save(idx)
        if failed:
            return (True,
                    f"Destroyed {deleted} item(s), {len(failed)} failed.",
                    {"deleted": deleted, "failed": failed, "freed": freed})
        return (True, f"Destroyed {deleted} item(s). Quarantine is now empty.",
                {"deleted": deleted, "failed": [], "freed": freed})
    except Exception as e:  # noqa: BLE001
        return False, f"Destroy All failed: {e}", {
            "deleted": 0, "failed": [], "freed": 0}


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
            ok, _msg = _remove_path(stored_abs)
            if ok:
                freed += item.get("size", 0)
                removed += 1
            else:
                kept.append(item)  # delete failed -> keep + report via UI
        else:
            kept.append(item)
    idx["items"] = kept
    _save(idx)
    return removed, freed
