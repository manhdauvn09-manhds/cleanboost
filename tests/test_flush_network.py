"""Tests for Flush Network (v2.6.0) + Network tab layout.

Flush Network clears stale DNS / NetBIOS / ARP caches WITHOUT
disconnecting (unlike Quick Refresh, which release+renews the IP).
Admin-only steps are skipped with a note when not admin.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from network import refresh as net_refresh  # noqa: E402


class TestFlushNetwork(unittest.TestCase):
    def _run(self, admin, verify=(True, "OK")):
        """Run flush_network with mocked _is_admin/_run/_verify."""
        def fake_run(argv, timeout=30, **_kw):
            return True, "OK", ""

        with mock.patch.object(net_refresh, "_is_admin",
                               return_value=admin), \
                mock.patch.object(net_refresh, "_run",
                                  side_effect=fake_run), \
                mock.patch.object(net_refresh, "_verify",
                                  return_value=verify):
            with mock.patch.object(sys, "platform", "win32"):
                return net_refresh.flush_network()

    def test_non_windows_refused(self):
        with mock.patch.object(sys, "platform", "linux"):
            ok, msg, steps = net_refresh.flush_network()
        self.assertFalse(ok)
        self.assertIn("Windows", msg)
        self.assertEqual(len(steps), 1)

    def test_non_admin_skips_admin_steps_but_succeeds(self):
        ok, msg, steps = self._run(admin=False)
        self.assertTrue(ok)
        by_name = {s["step"]: s for s in steps}
        self.assertFalse(by_name["flushdns"]["skipped"])
        self.assertTrue(by_name["flushdns"]["ok"])
        for name in ("netbios", "arp", "arpcache"):
            self.assertTrue(by_name[name]["skipped"], name)
            self.assertTrue(by_name[name]["ok"], name)
        self.assertTrue(by_name["verify"]["ok"])
        self.assertIn("Administrator", msg)

    def test_admin_runs_all_steps(self):
        ok, _msg, steps = self._run(admin=True)
        self.assertTrue(ok)
        self.assertEqual([s["step"] for s in steps],
                         ["flushdns", "netbios", "arp", "arpcache", "verify"])
        self.assertTrue(all(not s["skipped"] for s in steps))

    def test_failed_step_reports_failure(self):
        def fake_run(argv, timeout=30, **_kw):
            if argv[0] == "arp":
                return False, "Access denied", ""
            return True, "OK", ""

        with mock.patch.object(net_refresh, "_is_admin",
                               return_value=True), \
                mock.patch.object(net_refresh, "_run",
                                  side_effect=fake_run), \
                mock.patch.object(net_refresh, "_verify",
                                  return_value=(True, "OK")):
            with mock.patch.object(sys, "platform", "win32"):
                ok, msg, steps = net_refresh.flush_network()
        self.assertFalse(ok)
        self.assertIn("arp", msg)

    def test_verify_failed_is_warning_not_failure(self):
        ok, msg, _steps = self._run(admin=True, verify=(False, "no ping"))
        self.assertTrue(ok)
        self.assertIn("verify failed", msg.lower())


class TestNetTabLayout(unittest.TestCase):
    def test_four_subtabs_exist(self):
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "ui", "app.py")
        with open(path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("CTkTabview", src)
        for tab in ("Overview", "Test & Diagnose", "DNS & Refresh", "Repair"):
            self.assertIn(f'tabs.add("{tab}")', src)
        for fn in ("_build_net_overview", "_build_net_test",
                   "_build_net_dns", "_build_net_repair",
                   "_flush_network", "_open_network_guide"):
            self.assertIn(f"def {fn}", src)


if __name__ == "__main__":
    unittest.main()
