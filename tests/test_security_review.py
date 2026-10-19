"""Security review tests (v2.5.2).

Covers: quarantine-mode skip for irreversible specials, medium-confidence
orphans quarantine-only, restore-point prune by timestamp + SystemDrive,
and the expanded protected-process list.
Run:  python -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleaner.clean import _clean_special, _clean_special2, clean_rules  # noqa: E402
from cleaner import sysclean  # noqa: E402
from cleaner import quarantine as Q  # noqa: E402
from safety import protected  # noqa: E402


def _win32(test_fn):
    def wrapper(self):
        with mock.patch.object(sys, "platform", "win32"):
            return test_fn(self)
    return wrapper


class TestQuarantineModeSkip(unittest.TestCase):
    @_win32
    def test_recycle_bin_skipped_in_quarantine_mode(self):
        ok, msg, _freed, _stats = _clean_special(
            {"special": "recycle_bin", "id": "win_recycle_bin"},
            permanent=False)
        self.assertFalse(ok)
        self.assertIn("Skipped in Quarantine mode", msg)

    def test_update_cache_skipped_in_quarantine_mode(self):
        ok, msg, _freed, _stats = _clean_special2(
            {"special": "update_cache", "id": "win_update_cache"},
            permanent=False)
        self.assertFalse(ok)
        self.assertIn("Skipped in Quarantine mode", msg)

    def test_dism_resetbase_skipped_in_quarantine_mode(self):
        ok, _msg, _freed, _stats = _clean_special2(
            {"special": "dism_resetbase", "id": "win_dism_resetbase"},
            permanent=False)
        self.assertFalse(ok)

    def test_clean_rules_reports_skip_in_summary(self):
        rule = {"id": "win_update_cache", "name": "Windows Update download cache",
                "special": "update_cache", "level": 2, "requires_admin": True}
        results = [{"rule": rule, "size": 0, "files": [], "dirs": [],
                    "note": ""}]
        summary = clean_rules(results, {"win_update_cache"},
                              permanent=False, level=2)
        specials = summary.get("specials", [])
        self.assertEqual(len(specials), 1)
        self.assertFalse(specials[0]["ok"])
        self.assertIn("Skipped in Quarantine mode", specials[0]["message"])


class TestOrphanConfidence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch("cleaner.quarantine.root", return_value=self.tmp.name)
        p.start()
        self.addCleanup(p.stop)

    def _make_dir(self, name):
        d = os.path.join(self.tmp.name, name)
        os.makedirs(d)
        with open(os.path.join(d, "f.txt"), "w") as f:
            f.write("data")
        return d

    def test_medium_orphan_quarantined_even_in_delete_mode(self):
        high = self._make_dir("high_app")
        med = self._make_dir("med_app")
        res = {"orphans": [
            {"path": high, "size": 10, "confidence": "high"},
            {"path": med, "size": 20, "confidence": "medium"}]}
        rule = {"special": "orphan_apps", "id": "win_orphan_apps"}
        ok, msg, freed, stats = _clean_special2(rule, res, permanent=True)
        self.assertTrue(ok)
        self.assertFalse(os.path.exists(high))  # high: really deleted
        self.assertFalse(os.path.exists(med))   # medium: moved, not deleted
        self.assertEqual(len(Q.list_items()), 1)  # medium sits in quarantine
        self.assertEqual(Q.list_items()[0]["orig"], med)
        self.assertEqual(stats["deleted"], 1)
        self.assertEqual(stats["quarantined"], 1)
        self.assertEqual(freed, 10)  # medium bytes still on disk: not "freed"
        self.assertIn("quarantined, not deleted", msg)

    def test_high_orphan_quarantined_in_quarantine_mode(self):
        high = self._make_dir("high_app2")
        res = {"orphans": [{"path": high, "size": 10, "confidence": "high"}]}
        rule = {"special": "orphan_apps", "id": "win_orphan_apps"}
        ok, _msg, freed, stats = _clean_special2(rule, res, permanent=False)
        self.assertTrue(ok)
        self.assertEqual(stats["quarantined"], 1)
        self.assertEqual(stats["deleted"], 0)
        self.assertEqual(len(Q.list_items()), 1)


class TestPruneRestorePoints(unittest.TestCase):
    FAKE_OUT = """
Contents of shadow copy set ID: {BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB}
   Original Volume: (C:)\\\\?\\Volume{1111}\\
   Creation Time: 10/15/2026 3:00:00 AM
   Shadow Copy ID: {AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA}

Contents of shadow copy set ID: {CCCCCCCC-CCCC-CCCC-CCCC-CCCCCCCCCCCC}
   Original Volume: (C:)\\\\?\\Volume{1111}\\
   Creation Time: 10/10/2026 3:00:00 AM
   Shadow Copy ID: {DDDDDDDD-DDDD-DDDD-DDDD-DDDDDDDDDDDD}

Contents of shadow copy set ID: {EEEEEEEE-EEEE-EEEE-EEEE-EEEEEEEEEEEE}
   Original Volume: (D:)\\\\?\\Volume{2222}\\
   Creation Time: 10/01/2026 3:00:00 AM
   Shadow Copy ID: {FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF}
"""

    @_win32
    def test_keeps_newest_by_timestamp_and_system_drive_only(self):
        deleted = []

        def fake_run(argv, timeout=120):
            if "list" in argv:
                return 0, self.FAKE_OUT
            if "delete" in argv:
                deleted.append(argv[-2])
                return 0, ""
            return 1, ""

        with mock.patch("cleaner.sysclean._run", side_effect=fake_run), \
             mock.patch("cleaner.sysclean.privilege.is_admin",
                        return_value=True):
            ok, msg, _freed = sysclean.prune_old_restore_points()
        self.assertTrue(ok)
        # NEW-C listed FIRST but is newest -> kept; OLD-D is on D: -> kept.
        self.assertEqual(deleted, ["/shadow={DDDDDDDD-DDDD-DDDD-DDDD-DDDDDDDDDDDD}"])
        self.assertIn("Deleted 1/1", msg)

    @_win32
    def test_undated_copies_are_kept(self):
        out = """
Contents of shadow copy set ID: {BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB}
   Original Volume: (C:)\\\\?\\Volume{1111}\\
   Creation Time: 10/15/2026 3:00:00 AM
   Shadow Copy ID: {AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA}

Contents of shadow copy set ID: {CCCCCCCC-CCCC-CCCC-CCCC-CCCCCCCCCCCC}
   Original Volume: (C:)\\\\?\\Volume{1111}\\
   Shadow Copy ID: {11111111-2222-3333-4444-555555555555}
"""
        deleted = []

        def fake_run(argv, timeout=120):
            if "list" in argv:
                return 0, out
            deleted.append(argv)
            return 0, ""

        with mock.patch("cleaner.sysclean._run", side_effect=fake_run), \
             mock.patch("cleaner.sysclean.privilege.is_admin",
                        return_value=True):
            ok, _msg, _freed = sysclean.prune_old_restore_points()
        self.assertTrue(ok)
        self.assertEqual(deleted, [])  # undated copy kept, not deleted


class TestProtectedProcesses(unittest.TestCase):
    def test_svchost_and_trustedinstaller_blocked(self):
        self.assertEqual(protected.check_process("svchost.exe", 1), "block")
        self.assertEqual(protected.check_process("trustedinstaller.exe", 1),
                         "block")

    def test_defender_engine_blocked(self):
        # msmpeng.exe is covered by the anti-malware block rule:
        # killing the Defender engine is malware behaviour.
        self.assertEqual(protected.check_process("msmpeng.exe", 1), "block")

    def test_normal_process_ok(self):
        self.assertEqual(protected.check_process("notepad.exe", 12345), "ok")


if __name__ == "__main__":
    unittest.main()
