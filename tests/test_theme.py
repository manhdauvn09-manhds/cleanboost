"""Regression test for the v2.5.4 startup crash.

v2.5.3 shipped a NameError (C_BTN2_HOV_BTN_HOV) created by a bulk
string replacement: 'hover_color=C_ACC' also matched inside
'hover_color=C_ACC_BTN_HOV'. The GUI crashed while building the
Cleaner page, and pythonw.exe hid the traceback, so the app just
never appeared. This test fails on any undefined C_* name in
ui/app.py, so the same class of bug can never ship silently again.
"""
import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ui.app as app  # noqa: E402


class TestThemeConstants(unittest.TestCase):
    def test_no_undefined_c_constants(self):
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "ui", "app.py")
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        defined = set(dir(app))
        missing = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id.startswith("C_"):
                if node.id not in defined:
                    missing.add(node.id)
        self.assertFalse(missing, f"Undefined theme constants: {missing}")

    def test_button_palette_constants_exist(self):
        for name in ("C_BTN2", "C_BTN2_TXT", "C_BTN2_HOV",
                     "C_ACC_BTN", "C_ACC_BTN_HOV", "C_ONCOLOR"):
            self.assertTrue(getattr(app, name, ""), f"{name} is empty/missing")


if __name__ == "__main__":
    unittest.main()
