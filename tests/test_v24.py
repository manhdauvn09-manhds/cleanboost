"""Unit tests for CleanBoost v2.4 (network + health + optimize).

All Windows-only commands are mocked — these tests run on Linux too.
Run:  python -m unittest discover -s tests -v
"""
import sys
import os
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from safety import protected  # noqa: E402
from network import info as net_info, ports as net_ports  # noqa: E402
from network import speed as net_speed, refresh as net_refresh  # noqa: E402
from core import health as health_mod  # noqa: E402


class TestPortSeverity(unittest.TestCase):
    def test_sensitive_on_lan_is_critical(self):
        self.assertEqual(protected.port_severity(3389, "0.0.0.0"), "critical")
        self.assertEqual(protected.port_severity(22, "0.0.0.0"), "normal")

    def test_sensitive_on_localhost_is_warning(self):
        self.assertEqual(protected.port_severity(445, "127.0.0.1"), "warning")

    def test_ordinary_port_is_normal(self):
        self.assertEqual(protected.port_severity(8080, "0.0.0.0"), "normal")


class TestPorts(unittest.TestCase):
    def _fake_conn(self, port, ip, pid, status="LISTEN"):
        c = mock.Mock()
        c.status = status
        c.laddr = mock.Mock(port=port, ip=ip)
        c.pid = pid
        return c

    @mock.patch("network.ports.psutil.net_connections")
    @mock.patch("network.ports.psutil.Process")
    def test_list_and_ssh(self, mock_proc, mock_conns):
        mock_conns.return_value = [
            self._fake_conn(22, "0.0.0.0", 1234),
            self._fake_conn(5432, "127.0.0.1", 5678),
            self._fake_conn(8080, "0.0.0.0", 9999, status="ESTABLISHED"),
        ]
        mock_proc.side_effect = lambda pid: mock.Mock(
            **{"name.return_value": {1234: "sshd.exe",
                                     5678: "postgres.exe"}[pid]})
        ok, _msg, rows = net_ports.list_listening_ports()
        self.assertTrue(ok)
        self.assertEqual(len(rows), 2)  # ESTABLISHED filtered out
        ssh = [r for r in rows if r["port"] == 22][0]
        self.assertEqual(ssh["process"], "sshd.exe")
        self.assertEqual(ssh["scope"], "LAN")
        pg = [r for r in rows if r["port"] == 5432][0]
        self.assertEqual(pg["level"], "warning")  # sensitive + localhost
        ok, msg, data = net_ports.check_ssh()
        self.assertTrue(data["open"])
        self.assertIn("OPEN", msg)

    @mock.patch("network.ports.psutil.net_connections")
    def test_ssh_closed(self, mock_conns):
        mock_conns.return_value = [self._fake_conn(80, "0.0.0.0", 111)]
        _ok, _msg, data = net_ports.check_ssh()
        self.assertFalse(data["open"])

    def test_port_guide(self):
        self.assertIn("Remote Desktop", net_ports.get_port_guide(3389))
        self.assertIn("Port 9999", net_ports.get_port_guide(9999))


class TestInfo(unittest.TestCase):
    @mock.patch("network.info._global_ip", return_value=("1.2.3.4", "x"))
    @mock.patch("network.info._gateway", return_value="192.168.1.1")
    @mock.patch("network.info._dns", return_value=["1.1.1.1"])
    @mock.patch("network.info._wifi", return_value=None)
    @mock.patch("network.info.psutil.net_if_addrs")
    @mock.patch("network.info.psutil.net_if_stats")
    def test_get_network_info(self, mock_stats, mock_addrs, *_):
        import socket
        addr = mock.Mock()
        addr.family = socket.AF_INET
        addr.address = "192.168.1.25"
        addr.netmask = "255.255.255.0"
        mac = mock.Mock()
        mac.family = 17
        mac.address = "AA:BB:CC:DD:EE:FF"
        mock_addrs.return_value = {"Wi-Fi": [addr, mac]}
        mock_stats.return_value = {"Wi-Fi": mock.Mock(isup=True)}
        ok, _msg, data = net_info.get_network_info()
        self.assertTrue(ok)
        self.assertEqual(data["local_ip"], "192.168.1.25")
        self.assertEqual(data["global_ip"], "1.2.3.4")
        self.assertEqual(data["gateway"], "192.168.1.1")
        self.assertEqual(data["dns"], ["1.1.1.1"])

    def test_gateway_parsers(self):
        route = (" 0.0.0.0          0.0.0.0      192.168.1.1   192.168.1.25\n")
        self.assertEqual(net_info._gateway_from_route_print(route), "192.168.1.1")
        ipc = "   Default Gateway . . . . . . . . . : 10.0.0.1\n"
        self.assertEqual(net_info._gateway_from_ipconfig(ipc), "10.0.0.1")


class TestSpeed(unittest.TestCase):
    @mock.patch("network.speed.subprocess.run")
    def test_ping_windows_parse(self, mock_run):
        mock_run.return_value = mock.Mock(
            stdout="Average = 12ms", returncode=0)
        with mock.patch("network.speed.sys.platform", "win32"):
            ok, _msg, ms = net_speed.ping_host("1.1.1.1")
        self.assertTrue(ok)
        self.assertEqual(ms, 12.0)

    @mock.patch("network.speed.subprocess.run")
    def test_ping_linux_parse(self, mock_run):
        mock_run.return_value = mock.Mock(
            stdout="rtt min/avg/max/mdev = 10.1/12.5/15.0/1.2 ms",
            returncode=0)
        with mock.patch("network.speed.sys.platform", "linux"):
            ok, _msg, ms = net_speed.ping_host("1.1.1.1")
        self.assertTrue(ok)
        self.assertEqual(ms, 12.5)

    @mock.patch("network.speed.ping_host", return_value=(True, "", 10.0))
    @mock.patch("network.speed.measure_dns_time", return_value=(True, "", 25.0))
    @mock.patch("network.speed.download_speed", return_value=(True, "", 50.0))
    def test_run_speed_test(self, *_):
        ok, _msg, res = net_speed.run_speed_test()
        self.assertTrue(ok)
        self.assertEqual(res["ping_1_1_1_1_ms"], 10.0)
        self.assertEqual(res["download_mbps"], 50.0)

    def test_format_speed_none_safe(self):
        s = net_speed.format_speed({})
        self.assertIn("-", s)


class TestRefresh(unittest.TestCase):
    @mock.patch("network.refresh.sys.platform", "linux")
    def test_requires_windows(self):
        ok, _msg, steps = net_refresh.quick_refresh()
        self.assertFalse(ok)
        self.assertEqual(steps[0]["step"], "flushdns")

    @mock.patch("network.refresh._run", return_value=(True, "OK", ""))
    @mock.patch("network.refresh._verify", return_value=(True, "OK"))
    @mock.patch("network.refresh.sys.platform", "win32")
    def test_quick_refresh_success(self, *_):
        ok, _msg, steps = net_refresh.quick_refresh()
        self.assertTrue(ok)
        self.assertEqual([s["step"] for s in steps],
                         ["flushdns", "release", "renew", "verify"])

    @mock.patch("network.refresh._run",
                side_effect=[(True, "OK", ""), (False, "fail", ""),
                             (True, "OK", "")])
    @mock.patch("network.refresh._verify", return_value=(True, "OK"))
    @mock.patch("network.refresh.sys.platform", "win32")
    def test_quick_refresh_release_fails(self, *_):
        ok, msg, steps = net_refresh.quick_refresh()
        self.assertFalse(ok)
        self.assertIn("release", msg)


class TestHealth(unittest.TestCase):
    def test_formula(self):
        # RAM free 50% -> -15, disk free 80% -> -6, junk 5GB -> -20,
        # startup 10 -> -5, age 15d -> -5. Score = 100-51 = 49.
        ok, _msg, data = health_mod.compute_health(
            junk_bytes=5 * 1024 ** 3, startup_count=10, last_clean_days=15,
            ram_free_pct=50.0, disk_free_pct=80.0)
        self.assertTrue(ok)
        self.assertEqual(data["score"], 49)
        self.assertEqual(data["penalties"]["junk"], 20.0)

    def test_perfect_score(self):
        ok, _msg, data = health_mod.compute_health(
            junk_bytes=0, startup_count=0, last_clean_days=0,
            ram_free_pct=100.0, disk_free_pct=100.0)
        self.assertEqual(data["score"], 100)

    def test_junk_not_measured_zero_penalty(self):
        ok, _msg, data = health_mod.compute_health(
            junk_bytes=None, startup_count=0, last_clean_days=0,
            ram_free_pct=100.0, disk_free_pct=100.0)
        self.assertEqual(data["penalties"]["junk"], 0.0)
        self.assertFalse(data["junk_measured"])


class TestOptimize(unittest.TestCase):
    @mock.patch("core.optimize._ping", return_value=11.0)
    @mock.patch("core.memory_cleaner.light_clean", return_value=["trimmed"])
    @mock.patch("cleaner.engine.rules_for", return_value=[])
    @mock.patch("network.refresh.quick_refresh",
                return_value=(True, "done", []))
    def test_run_optimize(self, *_):
        from core import optimize as optimizer
        ok, _msg, report = optimizer.run_optimize()
        self.assertTrue(ok)
        self.assertTrue(report["refresh_ok"])
        self.assertEqual(report["ping_before_ms"], 11.0)
        self.assertIn("trimmed", report["messages"])


if __name__ == "__main__":
    unittest.main()
