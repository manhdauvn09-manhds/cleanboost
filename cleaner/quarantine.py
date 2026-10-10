"""Khu cách ly (Quarantine).

File bị dọn được CHUYỂN vào đây thay vì xóa ngay: giữ 14 ngày,
khôi phục 1-click về đúng chỗ cũ. Hết hạn mới xóa vĩnh viễn (có hỏi).
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
    """Chuyển 1 file hoặc thư mục vào khu cách ly. Trả về item đã lưu."""
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
    """Khôi phục file về chỗ cũ. Trả về (ok, message)."""
    idx = _load()
    item = next((i for i in idx["items"] if i["id"] == item_id), None)
    if not item:
        return False, "Không tìm thấy trong khu cách ly."
    stored_abs = os.path.join(root(), item["stored"])
    if not os.path.exists(stored_abs):
        return False, "File cách ly không còn tồn tại (có thể đã bị xóa tay)."
    os.makedirs(os.path.dirname(item["orig"]), exist_ok=True)
    dest = item["orig"]
    if os.path.exists(dest):
        # chỗ cũ đã có file mới -> không ghi đè, đổi tên
        dest = f"{dest}.restored_{item['id']}"
    shutil.move(stored_abs, dest)
    idx["items"] = [i for i in idx["items"] if i["id"] != item_id]
    _save(idx)
    return True, f"Đã khôi phục về: {dest}"


def delete_permanent(item_id: str):
    """Xóa vĩnh viễn 1 item trong khu cách ly."""
    idx = _load()
    item = next((i for i in idx["items"] if i["id"] == item_id), None)
    if not item:
        return False, "Không tìm thấy trong khu cách ly."
    stored_abs = os.path.join(root(), item["stored"])
    try:
        if os.path.isdir(stored_abs) and not os.path.islink(stored_abs):
            shutil.rmtree(stored_abs, ignore_errors=False)
        elif os.path.lexists(stored_abs):
            os.remove(stored_abs)
    except OSError as e:
        return False, f"Không xóa được: {e}"
    idx["items"] = [i for i in idx["items"] if i["id"] != item_id]
    _save(idx)
    return True, f"Đã xóa vĩnh viễn: {os.path.basename(item['orig'])}"


def purge_expired(days: int = RETENTION_DAYS):
    """Xóa vĩnh viễn các item quá hạn. Trả về (số item, dung lượng giải phóng)."""
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
            stored_abs = os.path.join(root(), item["stored"])
            try:
                if os.path.isdir(stored_abs) and not os.path.islink(stored_abs):
                    shutil.rmtree(stored_abs, ignore_errors=False)
                elif os.path.lexists(stored_abs):
                    os.remove(stored_abs)
                freed += item.get("size", 0)
                removed += 1
            except OSError:
                kept.append(item)  # xóa lỗi -> giữ lại
        else:
            kept.append(item)
    idx["items"] = kept
    _save(idx)
    return removed, freed
