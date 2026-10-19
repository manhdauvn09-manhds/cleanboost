"""Regression tests for the v2.5.5 Network-tab loading bug.

Bug: opening the Network tab fired _refresh_net_info() then
_refresh_ports() back to back; the busy-guard dropped the second
task, so the Port table stayed empty forever (and _net_loaded
blocked any retry). The tab looked dead: "Loading..." + empty ports.
"""
import ast
import os
import sys
import unittest
from unittest import mock
from urllib.error import URLError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from network import info as net_info  # noqa: E402


def _func_node(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


class TestNetworkTabLoad(unittest.TestCase):
    def test_show_page_uses_combined_network_load(self):
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "ui", "app.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        show = _func_node(tree, "_show_page")
        self.assertIsNotNone(show, "_show_page not found")
        called = set()
        for node in ast.walk(show):
            if isinstance(node, ast.Call) and isinstance(
                    node.func, ast.Attribute):
                called.add(node.func.attr)
        self.assertIn("_refresh_network_all", called)
        # The old back-to-back pair must NOT be called from _show_page:
        # the busy-guard silently dropped the second one.
        self.assertNotIn("_refresh_net_info", called)
        self.assertNotIn("_refresh_ports", called)

    def test_refresh_network_all_exists(self):
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "ui", "app.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        self.assertIsNotNone(_func_node(tree, "_refresh_network_all"))

    def test_global_ip_offline_returns_empty(self):
        with mock.patch("network.info.urllib.request.urlopen",
                        side_effect=URLError("offline")):
            self.assertEqual(net_info._global_ip(), ("", ""))

    def test_get_network_info_degrades_without_global_ip(self):
        with mock.patch("network.info.urllib.request.urlopen",
                        side_effect=URLError("offline")):
            ok, msg, data = net_info.get_network_info()
            self.assertTrue(ok)
            self.assertEqual(data.get("global_ip"), "")
            self.assertIn("global_ip", msg)


if __name__ == "__main__":
    unittest.main()
