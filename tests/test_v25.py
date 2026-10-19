"""Unit tests for CleanBoost v2.5 (dns, diag, hogs, startup, refresh).

Windows-only paths are mocked — these tests run on Linux too.
Run:  python -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from network import dns as net_dns  # noqa: E402
from network import diag as net_diag  # noqa: E402
from network import hogs as net_hogs  # noqa: E402
from network import refresh as net_refresh  # noqa: E402
from core import startup as startup_mod  # noqa: E402


def _win32(test_fn):
    """Decorator: run the test with sys.platform faked to win32."""
    def wrapper(self):
        with mock.patch.object(sys, "platform", "win32"):
            return test_fn(self)
    return wrapper


class TestDns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _patch_env(self, admin=True):
        p1 = mock.patch("network.dns.privilege.is_admin", return_value=admin)
        p2 = mock.patch("network.dns._config_dir", return_value=self.tmp.name)
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)

    @_win32
    def test_set_dns_saves_backup_first(self):
        self._patch_env(admin=True)
        calls = []
        with mock.patch("network.dns.get_current_dns",
                        return_value=(True, "", {"adapter": "Wi-Fi",
                                                 "dns": ["9.9.9.9"]})), \
             mock.patch("network.dns._run",
                        side_effect=lambda argv, timeout=30: (
                            calls.append(argv), (0, ""))[1]):
            ok, msg = net_dns.set_dns("1.1.1.1", "1.0.0.1", adapter="Wi-Fi")
        self.assertTrue(ok)
        self.assertIn("Undo", msg)
        backup = net_dns.backup_info()
        self.assertEqual(backup["dns"], ["9.9.9.9"])
        self.assertTrue(any("static" in c and "1.1.1.1" in c for c in calls))

    @_win32
    def test_restore_dns_uses_backup(self):
        self._patch_env(admin=True)
        with open(os.path.join(self.tmp.name, "dns_backup.json"), "w") as f:
            f.write('{"adapter": "Wi-Fi", "dns": ["8.8.8.8", "8.8.4.4"]}')
        calls = []
        with mock.patch("network.dns._run",
                        side_effect=lambda argv, timeout=30: (
                            calls.append(argv), (0, ""))[1]):
            ok, msg = net_dns.restore_dns()
        self.assertTrue(ok)
        self.assertIn("8.8.8.8", msg)
        self.assertTrue(any("8.8.8.8" in c for c in calls))

    @_win32
    def test_restore_dns_without_backup_fails(self):
        self._patch_env(admin=True)
        ok, _msg = net_dns.restore_dns()
        self.assertFalse(ok)

    def test_set_dns_without_admin_refused(self):
        self._patch_env(admin=False)
        ok, msg = net_dns.set_dns("1.1.1.1")
        self.assertFalse(ok)
        self.assertIn("Admin", msg)

    def test_measure_dns_sorted(self):
        with mock.patch("network.dns._run", return_value=(0, "")):
            ok, msg, results = net_dns.measure_dns(tries=1)
        self.assertTrue(ok)
        self.assertIn("Fastest", msg)
        avgs = [r["avg_ms"] for r in results if r["ok"]]
        self.assertEqual(avgs, sorted(avgs))


class TestDiag(unittest.TestCase):
    def _setup(self, gateway_ms, ext_ms, dns_ms, gateway="192.168.1.1"):
        def ping(host, count=2, timeout=20):
            if host == gateway:
                return (gateway_ms is not None, "", gateway_ms)
            return (ext_ms is not None, "", ext_ms)
        p1 = mock.patch("network.diag.net_speed.ping_host", side_effect=ping)
        p2 = mock.patch("network.diag.net_speed.measure_dns_time",
                        return_value=(dns_ms is not None, "", dns_ms))
        p3 = mock.patch("network.diag.net_info.get_network_info",
                        return_value=(True, "", {"gateway": gateway,
                                                 "wifi": None}))
        p4 = mock.patch("network.diag.psutil.net_connections", return_value=[])
        for p in (p1, p2, p3, p4):
            p.start()
            self.addCleanup(p.stop)

    def test_gateway_down_means_lan_problem(self):
        self._setup(None, 20.0, 30.0)
        _ok, _msg, data = net_diag.run_diagnostics()
        self.assertIn("WiFi/LAN", data["conclusion"])

    def test_external_slow_means_isp(self):
        self._setup(10.0, 500.0, 30.0)
        _ok, _msg, data = net_diag.run_diagnostics()
        self.assertIn("ISP", data["conclusion"])

    def test_dns_slow_means_dns(self):
        self._setup(10.0, 20.0, 900.0)
        _ok, _msg, data = net_diag.run_diagnostics()
        self.assertIn("DNS", data["conclusion"])

    def test_all_fine(self):
        self._setup(10.0, 20.0, 30.0)
        _ok, _msg, data = net_diag.run_diagnostics()
        self.assertIn("looks fine", data["conclusion"])


class TestHogs(unittest.TestCase):
    def test_rows_ranked_by_connections(self):
        seq = {"n": 0}

        def fake_counters(pernic=True):
            seq["n"] += 1
            c = mock.Mock()
            c.bytes_sent = 1000 + 3000 * seq["n"]
            c.bytes_recv = 2000 + 6000 * seq["n"]
            return {"eth0": c}

        def conn(pid, status="ESTABLISHED", ip="1.2.3.4"):
            m = mock.Mock()
            m.status = status
            m.pid = pid
            m.raddr = mock.Mock(ip=ip)
            return m

        conns = [conn(111, ip="1.1.1.1"), conn(111, ip="1.1.1.2"),
                 conn(222, ip="8.8.8.8")]
        with mock.patch("network.hogs.psutil.net_io_counters",
                        side_effect=fake_counters), \
             mock.patch("network.hogs.time.sleep", return_value=None), \
             mock.patch("network.hogs.time.monotonic",
                        side_effect=[0.0, 3.0]), \
             mock.patch("network.hogs.psutil.net_connections",
                        return_value=conns), \
             mock.patch("network.hogs.psutil.Process",
                        side_effect=lambda pid: mock.Mock(
                            **{"name.return_value": {111: "chrome.exe",
                                                     222: "steam.exe"}[pid]})):
            ok, _msg, data = net_hogs.get_bandwidth_hogs(interval=3.0)
        self.assertTrue(ok)
        self.assertEqual(data["rows"][0]["process"], "chrome.exe")
        self.assertEqual(data["rows"][0]["connections"], 2)
        self.assertAlmostEqual(data["recv_per_sec"], 6000 / 3.0)


class TestStartup(unittest.TestCase):
    def test_protected_detection(self):
        self.assertTrue(startup_mod._is_protected("SecurityHealth", "C:\\x.exe"))
        self.assertTrue(startup_mod._is_protected("Realtek Audio", "C:\\x.exe"))
        self.assertFalse(startup_mod._is_protected("Spotify", "C:\\spotify.exe"))

    def test_list_startup_linux_is_windows_only(self):
        ok, msg, items = startup_mod.list_startup()
        self.assertFalse(ok)
        self.assertEqual(items, [])

    @_win32
    def test_registry_toggle_roundtrip_with_fake_winreg(self):
        fake = types.ModuleType("winreg")
        fake.HKEY_CURRENT_USER = "HKCU"
        fake.HKEY_LOCAL_MACHINE = "HKLM"
        fake.KEY_READ = 1
        fake.KEY_SET_VALUE = 2
        store = {"HKCU": {"Spotify": ("C:\\spotify.exe", 1)}, "HKLM": {}}

        class Key:
            def __init__(self, d):
                self.d = d
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        def open_key(hive, sub, *a, **k):
            return Key(store[hive])

        def query_info_key(key):
            return (0, len(key.d), None)

        def enum_value(key, i):
            name = sorted(key.d)[i]
            return name, key.d[name][0], key.d[name][1]

        def query_value_ex(key, name):
            if name not in key.d:
                raise OSError("not found")
            return key.d[name]

        def set_value_ex(key, name, _r, typ, value):
            key.d[name] = (value, typ)

        def delete_value(key, name):
            del key.d[name]

        fake.OpenKey = open_key
        fake.QueryInfoKey = query_info_key
        fake.EnumValue = enum_value
        fake.QueryValueEx = query_value_ex
        fake.SetValueEx = set_value_ex
        fake.DeleteValue = delete_value

        with mock.patch.dict(sys.modules, {"winreg": fake}), \
             mock.patch("core.startup.privilege.is_admin", return_value=True), \
             mock.patch("core.startup._startup_folders", return_value=[]):
            ok, _msg, items = startup_mod.list_startup()
            self.assertTrue(ok)
            self.assertEqual(len(items), 1)
            self.assertTrue(items[0]["enabled"])
            ok, _msg = startup_mod.set_enabled("Spotify", "HKCU Run", False)
            self.assertTrue(ok)
            _ok, _msg, items = startup_mod.list_startup()
            self.assertEqual(items[0]["key"], "CleanBoost_disabled_Spotify")
            self.assertFalse(items[0]["enabled"])
            ok, _msg = startup_mod.set_enabled(
                "CleanBoost_disabled_Spotify", "HKCU Run", True)
            self.assertTrue(ok)
            _ok, _msg, items = startup_mod.list_startup()
            self.assertEqual(items[0]["key"], "Spotify")
            self.assertTrue(items[0]["enabled"])


class TestRefreshV25(unittest.TestCase):
    @_win32
    def test_adapter_reset_without_admin_refused(self):
        with mock.patch("network.refresh._is_admin", return_value=False):
            ok, msg, _steps = net_refresh.adapter_reset(adapter="Wi-Fi")
        self.assertFalse(ok)
        self.assertIn("Admin", msg)

    @_win32
    def test_adapter_reset_cancelled(self):
        import threading
        ev = threading.Event()
        ev.set()
        with mock.patch("network.refresh._is_admin", return_value=True):
            ok, _msg, _steps = net_refresh.adapter_reset(
                adapter="Wi-Fi", cancel_event=ev)
        self.assertFalse(ok)

    @_win32
    def test_adapter_reset_success(self):
        with mock.patch("network.refresh._is_admin", return_value=True), \
             mock.patch("network.refresh._powershell",
                        return_value=(True, "OK", "")), \
             mock.patch("network.refresh._ping_once", return_value=True), \
             mock.patch("psutil.net_if_stats",
                        return_value={"Wi-Fi": mock.Mock(isup=True)}), \
             mock.patch("time.sleep", return_value=None):
            ok, _msg, steps = net_refresh.adapter_reset(adapter="Wi-Fi")
        self.assertTrue(ok)
        self.assertEqual([s["step"] for s in steps],
                         ["disable", "wait", "enable", "verify"])

    @_win32
    def test_adapter_reset_verify_failed_returns_three_values(self):
        # v2.5.6 regression: the verify-failed path returned a 2-tuple
        # (message, steps) nested inside another tuple, so the UI's
        # `ok, msg, steps = res` unpack crashed.
        with mock.patch("network.refresh._is_admin", return_value=True), \
             mock.patch("network.refresh._powershell",
                        return_value=(True, "OK", "")), \
             mock.patch("network.refresh._ping_once", return_value=False), \
             mock.patch("psutil.net_if_stats",
                        return_value={"Wi-Fi": mock.Mock(isup=True)}), \
             mock.patch("time.sleep", return_value=None):
            ok, msg, steps = net_refresh.adapter_reset(adapter="Wi-Fi")
        self.assertFalse(ok)
        self.assertIn("30s", msg)
        self.assertEqual(steps[-1]["step"], "verify")

    @_win32
    def test_deep_reset_success(self):
        with mock.patch("network.refresh._is_admin", return_value=True), \
             mock.patch("network.refresh._run", return_value=(True, "OK", "")):
            ok, msg, steps = net_refresh.deep_reset()
        self.assertTrue(ok)
        self.assertIn("RESTART", msg)
        self.assertEqual(len(steps), 2)


if __name__ == "__main__":
    unittest.main()
