"""Unit tests for Quarantine delete / destroy (v2.5.1).

Covers: delete_permanent, delete_all (incl. failures + stale entries),
purge_expired, and the read-only retry helper. Runs on Linux too.
Run:  python -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleaner import quarantine as Q  # noqa: E402


class QuarantineCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch("cleaner.quarantine.root", return_value=self.tmp.name)
        p.start()
        self.addCleanup(p.stop)

    def _make_source(self, name, content=b"x" * 100):
        src = os.path.join(self.tmp.name, "src_" + name)
        os.makedirs(src, exist_ok=True)
        fp = os.path.join(src, name)
        with open(fp, "wb") as f:
            f.write(content)
        return fp

    def test_delete_permanent_removes_file_and_index(self):
        item = Q.put(self._make_source("a.txt"))
        self.assertEqual(len(Q.list_items()), 1)
        ok, _msg = Q.delete_permanent(item["id"])
        self.assertTrue(ok)
        self.assertEqual(Q.list_items(), [])

    def test_delete_permanent_dir_tree_with_readonly_file(self):
        src_dir = os.path.join(self.tmp.name, "srcdir")
        os.makedirs(os.path.join(src_dir, "sub"))
        fp = os.path.join(src_dir, "sub", "ro.txt")
        with open(fp, "w") as f:
            f.write("readonly")
        os.chmod(fp, 0o444)
        item = Q.put(src_dir)
        ok, _msg = Q.delete_permanent(item["id"])
        self.assertTrue(ok)
        self.assertEqual(Q.list_items(), [])

    def test_delete_permanent_missing_file_drops_index_entry(self):
        item = Q.put(self._make_source("gone.txt"))
        stored = os.path.join(self.tmp.name, item["stored"])
        os.remove(stored)  # user deleted it manually outside the app
        ok, _msg = Q.delete_permanent(item["id"])
        self.assertTrue(ok)
        self.assertEqual(Q.list_items(), [])

    def test_delete_permanent_unknown_id(self):
        ok, _msg = Q.delete_permanent("nope")
        self.assertFalse(ok)

    def test_delete_all_empties_everything(self):
        for name in ("a.txt", "b.txt", "c.txt"):
            Q.put(self._make_source(name))
        ok, _msg, summary = Q.delete_all()
        self.assertTrue(ok)
        self.assertEqual(summary["deleted"], 3)
        self.assertEqual(summary["failed"], [])
        self.assertEqual(Q.list_items(), [])

    def test_delete_all_reports_failures_and_keeps_them(self):
        i1 = Q.put(self._make_source("ok.txt"))
        i2 = Q.put(self._make_source("locked.txt"))
        real_remove = Q._remove_path

        def flaky(path):
            if "locked" in path:
                return False, "Could not delete file: [Errno 13] Permission denied"
            return real_remove(path)

        with mock.patch("cleaner.quarantine._remove_path", side_effect=flaky):
            ok, msg, summary = Q.delete_all()
        self.assertTrue(ok)
        self.assertIn("1 failed", msg)
        self.assertEqual(summary["deleted"], 1)
        self.assertEqual(len(summary["failed"]), 1)
        self.assertEqual(summary["failed"][0][1], "locked.txt")
        remaining = Q.list_items()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["id"], i2["id"])
        self.assertNotEqual(remaining[0]["id"], i1["id"])

    def test_purge_expired_only_old_items(self):
        from datetime import datetime, timedelta, timezone
        old = Q.put(self._make_source("old.txt"))
        new = Q.put(self._make_source("new.txt"))
        # Backdate the old item's index entry by 20 days.
        idx_path = os.path.join(self.tmp.name, "index.json")
        import json
        with open(idx_path, encoding="utf-8") as f:
            idx = json.load(f)
        for it in idx["items"]:
            if it["id"] == old["id"]:
                it["quarantined_at"] = (
                    datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump(idx, f)
        n, _freed = Q.purge_expired()
        self.assertEqual(n, 1)
        remaining = Q.list_items()
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["id"], new["id"])

    def test_remove_path_missing_is_ok(self):
        ok, _msg = Q._remove_path(os.path.join(self.tmp.name, "nope"))
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
