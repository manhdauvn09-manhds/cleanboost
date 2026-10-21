"""Kill-path unit tests (v2.7.0) — real processes, no GUI.

Proves process_manager.kill_process genuinely terminates a live process
(the user's "kill doesn't work" report traced to the UI busy-lock
cascade, not to this function — these tests lock the behavior in).
"""
import subprocess
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psutil  # noqa: E402
from core import process_manager as pm  # noqa: E402


def _spawn_sleeper():
    return subprocess.Popen([sys.executable, "-c",
                             "import time; time.sleep(60)"])


class TestKillProcess(unittest.TestCase):
    def test_kill_terminates_real_process(self):
        proc = _spawn_sleeper()
        try:
            self.assertTrue(psutil.pid_exists(proc.pid))
            ok, msg = pm.kill_process(proc.pid, force=False)
            self.assertTrue(ok, msg)
            proc.wait(timeout=5)
            self.assertIsNotNone(proc.poll())
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_force_kill_terminates(self):
        proc = _spawn_sleeper()
        try:
            ok, msg = pm.kill_process(proc.pid, force=True)
            self.assertTrue(ok, msg)
            proc.wait(timeout=5)
            self.assertIsNotNone(proc.poll())
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_kill_missing_pid_reports_failure(self):
        # find a pid that does not exist
        pid = 999999
        while psutil.pid_exists(pid):
            pid += 1
        ok, msg = pm.kill_process(pid, force=False)
        self.assertFalse(ok)
        self.assertTrue(msg)

    def test_list_processes_includes_sleeper(self):
        proc = _spawn_sleeper()
        try:
            time.sleep(0.2)
            rows = pm.list_processes(sort_by="memory", limit=300)
            self.assertIn(proc.pid, [r["pid"] for r in rows])
            top = pm.list_processes(sort_by="memory", limit=300)[:10]
            self.assertTrue(all("rss" in r and "cpu" in r for r in top))
        finally:
            proc.kill()


if __name__ == "__main__":
    unittest.main()
