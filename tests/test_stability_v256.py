"""Stability review tests (v2.5.6).

Covers the real bugs found by the full-feature audit:
- DNS change must abort when the backup cannot be saved.
- DNS measure must use a short timeout (was up to 135s).
- Scheduler commands must time out instead of hanging forever.
- Hog Finder must divide by the REAL elapsed time.
- Speed-test DNS fallback must give up after 5s (getaddrinfo has
  no timeout of its own).
- _run_bg must QUEUE tasks instead of silently dropping them.
"""
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cleaner import scheduler  # noqa: E402
from network import dns as net_dns  # noqa: E402
from network import hogs as net_hogs  # noqa: E402
from network import speed as net_speed  # noqa: E402


class TestDnsBackupRequired(unittest.TestCase):
    def _win(self):
        return mock.patch.object(sys, "platform", "win32")

    def test_set_dns_aborts_when_backup_fails(self):
        with self._win(), \
                mock.patch.object(net_dns.privilege, "is_admin",
                                  return_value=True), \
                mock.patch.object(net_dns, "get_active_adapter",
                                  return_value="Wi-Fi"), \
                mock.patch.object(net_dns, "get_current_dns",
                                  return_value=(True, "", {"dns": ["1.2.3.4"]})), \
                mock.patch.object(net_dns, "_save_backup",
                                  return_value=False), \
                mock.patch.object(net_dns, "_apply_static") as apply_mock:
            ok, msg = net_dns.set_dns("1.1.1.1", "1.0.0.1")
            self.assertFalse(ok)
            self.assertIn("backup", msg.lower())
            apply_mock.assert_not_called()

    def test_set_dns_auto_aborts_when_backup_fails(self):
        with self._win(), \
                mock.patch.object(net_dns.privilege, "is_admin",
                                  return_value=True), \
                mock.patch.object(net_dns, "get_active_adapter",
                                  return_value="Wi-Fi"), \
                mock.patch.object(net_dns, "get_current_dns",
                                  return_value=(True, "", {"dns": ["1.2.3.4"]})), \
                mock.patch.object(net_dns, "_save_backup",
                                  return_value=False), \
                mock.patch.object(net_dns, "_apply_dhcp") as apply_mock:
            ok, msg = net_dns.set_dns_auto()
            self.assertFalse(ok)
            self.assertIn("backup", msg.lower())
            apply_mock.assert_not_called()

    def test_measure_dns_uses_short_timeout(self):
        calls = []

        def fake_run(argv, timeout=None, **_kw):
            calls.append(timeout)
            return 0, ""

        with mock.patch.object(net_dns, "_run", side_effect=fake_run):
            ok, _msg, results = net_dns.measure_dns(
                tries=1, servers={"X": ("1.1.1.1", "1.0.0.1")})
        self.assertTrue(ok)
        self.assertTrue(calls)
        self.assertTrue(all(t == 5 for t in calls),
                        f"measure_dns timeouts: {calls}")


class TestSchedulerTimeout(unittest.TestCase):
    def test_status_survives_hung_schtasks(self):
        import subprocess as sp
        with mock.patch.object(scheduler.subprocess, "run",
                               side_effect=sp.TimeoutExpired("schtasks", 30)):
            ok, msg = scheduler.status()
            self.assertFalse(ok)
            self.assertIn("timed out", msg.lower())

    def test_install_windows_survives_hung_schtasks(self):
        import subprocess as sp
        with mock.patch.object(scheduler.privilege, "is_admin",
                               return_value=False), \
                mock.patch("os.path.exists", return_value=True), \
                mock.patch.object(scheduler.subprocess, "run",
                                  side_effect=sp.TimeoutExpired("schtasks", 30)):
            ok, msg = scheduler._install_windows()
            self.assertFalse(ok)
            self.assertIn("timed out", msg.lower())


class TestHogsElapsed(unittest.TestCase):
    def test_rate_uses_real_elapsed_time(self):
        with mock.patch.object(net_hogs, "_snapshot",
                               side_effect=[(1000, 2000), (4000, 8000)]), \
                mock.patch.object(net_hogs.time, "monotonic",
                                  side_effect=[100.0, 102.0]), \
                mock.patch.object(net_hogs.time, "sleep"), \
                mock.patch.object(net_hogs.psutil, "net_connections",
                                  return_value=[]):
            ok, _msg, data = net_hogs.get_bandwidth_hogs(interval=3.0)
        self.assertTrue(ok)
        # Real elapsed = 2s -> 3000/2 = 1500 up, 6000/2 = 3000 down.
        # The old code divided by the nominal 3s (1000 / 2000).
        self.assertAlmostEqual(data["sent_per_sec"], 1500.0)
        self.assertAlmostEqual(data["recv_per_sec"], 3000.0)


class TestDnsFallbackTimeout(unittest.TestCase):
    def test_getaddrinfo_fallback_gives_up_after_5s(self):
        def slow_getaddrinfo(*_a, **_kw):
            time.sleep(30)
            return []

        with mock.patch.object(net_speed.subprocess, "run",
                               side_effect=Exception("no nslookup")), \
                mock.patch("socket.getaddrinfo",
                           side_effect=slow_getaddrinfo):
            start = time.time()
            ok, msg, val = net_speed.measure_dns_time("google.com")
            elapsed = time.time() - start
        self.assertFalse(ok)
        self.assertIsNone(val)
        self.assertIn("timed out", msg.lower())
        self.assertLess(elapsed, 20, f"fallback took {elapsed:.1f}s")


class TestRunBgQueues(unittest.TestCase):
    def test_run_bg_queues_instead_of_dropping(self):
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "ui", "app.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("self._bg_queue.append", src)
        self.assertIn("self._bg_queue.pop(0)", src)
        # The old drop behavior must be gone.
        self.assertNotIn("Returns False if a task is already running.", src)


if __name__ == "__main__":
    unittest.main()
