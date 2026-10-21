"""v2.6.1 — stuck-task fixes: safe_walk (junction/depth guard) + UI watchdog.

Root cause class: os.walk follows Windows junctions (e.g. the AppData
"Application Data" self-junction), and if one disk-walking task never
finishes, _busy stays set and every button stays disabled forever.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cleaner import fs_walk  # noqa: E402


class TestSafeWalk(unittest.TestCase):
    def test_symlinked_dir_is_pruned(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "base"
            (base / "real").mkdir(parents=True)
            (base / "real" / "f.txt").write_text("x")
            (base / "link").symlink_to(base / "real",
                                       target_is_directory=True)
            first = next(iter(fs_walk.safe_walk(str(base))))
            dirs = first[1]
            self.assertIn("real", dirs)
            self.assertNotIn("link", dirs)

    def test_is_junction(self):
        with tempfile.TemporaryDirectory() as td:
            real = Path(td) / "real"
            real.mkdir()
            link = Path(td) / "link"
            link.symlink_to(real, target_is_directory=True)
            self.assertTrue(fs_walk.is_junction(str(link)))
            self.assertFalse(fs_walk.is_junction(str(real)))
            # cannot stat -> treated as junction (never descend blindly)
            self.assertTrue(fs_walk.is_junction(str(Path(td) / "gone")))

    def test_depth_cap(self):
        with tempfile.TemporaryDirectory() as td:
            cur = Path(td)
            for i in range(8):
                cur = cur / f"d{i}"
                cur.mkdir()
                (cur / "f.txt").write_text("x")
            seen_files = []
            for root, _d, files in fs_walk.safe_walk(td, max_depth=3):
                for fn in files:
                    seen_files.append(
                        os.path.relpath(os.path.join(root, fn), td))
            depths = [p.count(os.sep) for p in seen_files]
            # file at depth 3 (dirs d0..d2 + file) is seen, deeper is not
            self.assertIn(3, depths)
            self.assertTrue(all(d <= 3 for d in depths))

    def test_scan_rule_uses_safe_walk(self):
        src = (Path(__file__).resolve().parent.parent
               / "cleaner" / "scanner.py").read_text(encoding="utf-8")
        self.assertIn("safe_walk(base)", src)


class TestWatchdog(unittest.TestCase):
    def test_ui_watchdog_present(self):
        src = (Path(__file__).resolve().parent.parent
               / "ui" / "app.py").read_text(encoding="utf-8")
        # live elapsed-time status + 15-min stuck warning + task logging
        self.assertIn("_bg_poll", src)
        self.assertIn("bg_task_start", src)
        self.assertIn("bg_task_done", src)
        self.assertIn("bg_task_slow", src)
        # hard timeout abandonment (v2.7.0)
        self.assertIn("bg_task_timeout", src)
        self.assertIn("_abandon_bg", src)
        # worker threads never call Tk: results return via a polled
        # holder + the thread-safe UI queue (v2.7.0)
        self.assertIn("_post_ui", src)
        self.assertIn("_drain_ui_queue", src)
        # a worker dying with BaseException must release the UI lock
        self.assertIn("BaseException", src)


if __name__ == "__main__":
    unittest.main()
