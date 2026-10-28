"""Dialog tests (v2.7.1) — every popup must actually build, be modal,
and be closable.

Regression for the 28/10 report: the Cleaner "Delete" confirmation
showed a header + an EMPTY groups box and no buttons at all. Cause:
CTkFrame does not accept text_color, so the dialog constructor raised
ValueError on the first group row, aborting the dialog mid-build and
leaving a button-less zombie window on screen. These tests construct
every dialog class with realistic data and assert its content, its
grab (modal), and its Cancel/Confirm paths.

Run with:  xvfb-run -a python -m unittest tests.test_dialogs
Skipped automatically when no DISPLAY is available.
"""
import ast
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HAS_DISPLAY = bool(os.environ.get("DISPLAY"))


def collect_texts(w):
    out = []
    try:
        t = w.cget("text")
        if isinstance(t, str) and t:
            out.append(t)
    except Exception:
        pass
    for c in w.winfo_children():
        out.extend(collect_texts(c))
    return out


def pump(app, cond, timeout=10.0, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        app.update()
        if cond():
            return True
        time.sleep(step)
    app.update()
    return cond()


def find_button(w, text):
    import customtkinter as ctk
    if isinstance(w, ctk.CTkButton) and w.cget("text") == text:
        return w
    for c in w.winfo_children():
        hit = find_button(c, text)
        if hit is not None:
            return hit
    return None


class TestNoBadFrameKwargs(unittest.TestCase):
    def test_no_ctkframe_text_color(self):
        # CTkFrame has no text_color argument (v2.7.1 regression).
        src = (Path(__file__).resolve().parent.parent
               / "ui" / "app.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        bad = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "CTkFrame":
                    if any(kw.arg == "text_color" for kw in node.keywords):
                        bad.append(node.lineno)
        self.assertEqual(bad, [],
                         f"CTkFrame(text_color=...) at lines {bad}")


@unittest.skipUnless(HAS_DISPLAY, "needs a display (use xvfb-run)")
class TestDialogs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ui.app import App
        cls.app = App()
        cls.app.deiconify()
        cls.app.update()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        except Exception:
            pass

    def _items(self):
        return [
            ({"name": "User temp files", "impact": "Temp files, safe.",
              "warning": ""}, 3_294_000_000),
            ({"name": "Browser cache", "impact": "Re-downloaded.",
              "warning": ""}, 171_000_000),
            ({"name": "Thumbnail cache", "impact": "Rebuilt.",
              "warning": ""}, 10_000_000),
            ({"name": "Old IE/Edge web cache", "impact": "No effect.",
              "warning": ""}, 1_000_000),
            ({"name": "DirectX shader cache", "impact": "Recompiled.",
              "warning": ""}, 500_000),
        ]

    def test_confirm_dialog_lists_groups_and_is_modal(self):
        from ui.app import ConfirmCleanDialog
        dlg = ConfirmCleanDialog(self.app, self._items(), True)
        self.app.update()
        texts = collect_texts(dlg)
        for rule, _size in self._items():
            self.assertIn(rule["name"], texts,
                          f"group row missing: {rule['name']}")
        self.assertTrue(any("5 groups" in t for t in texts))
        self.assertIsNotNone(find_button(dlg, "Cancel"))
        self.assertIsNotNone(find_button(dlg, "Delete permanently"))
        self.assertIsNotNone(dlg.grab_status(),
                             "dialog did not hold the grab (not modal)")
        dlg._no()
        self.assertFalse(dlg.winfo_exists())
        self.assertFalse(dlg.result)

    def test_confirm_dialog_yes_path(self):
        from ui.app import ConfirmCleanDialog
        dlg = ConfirmCleanDialog(self.app, self._items(), False)
        self.app.update()
        self.assertIsNotNone(find_button(dlg, "Quarantine"))
        dlg._yes()
        self.assertTrue(dlg.result)
        self.assertFalse(dlg.winfo_exists())

    def test_high_risk_dialog(self):
        from ui.app import HighRiskConfirmDialog
        rules = [
            {"name": "DISM ResetBase", "impact": "Frees space.",
             "warning": "Cannot undo Windows Update cleanup.", "note": ""},
            {"name": "Disable hibernate", "impact": "Frees hiberfil.sys.",
             "warning": "Fast Startup turns off.", "note": ""},
        ]
        dlg = HighRiskConfirmDialog(self.app, rules)
        self.app.update()
        texts = collect_texts(dlg)
        self.assertIn("DISM ResetBase", texts)
        self.assertTrue(any("Cannot undo" in t for t in texts))
        run = find_button(dlg, "I understand — run high-risk actions")
        self.assertIsNotNone(run)
        self.assertEqual(str(run.cget("state")), "disabled")
        self.assertIsNotNone(dlg.grab_status())
        dlg._yes()
        self.assertTrue(dlg.result)

    def test_result_dialog(self):
        from ui.app import ResultDialog
        dlg = ResultDialog(self.app, "Cleanup finished",
                           "Freed 3.24 GB\n5 groups cleaned.")
        self.app.update()
        self.assertIsNotNone(dlg.grab_status())
        dlg.destroy()
        self.assertFalse(dlg.winfo_exists())

    def test_detail_dialog_lists_files(self):
        from ui.app import DetailDialog
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "a.tmp"
            p1.write_bytes(b"x" * 1000)
            p2 = Path(td) / "b.tmp"
            p2.write_bytes(b"y" * 2000)
            res = {"rule": {"name": "User temp files", "impact": ""},
                   "size": 3000, "paths": [str(p1), str(p2)]}
            dlg = DetailDialog(self.app, res)
            ok = pump(self.app,
                      lambda: len(dlg.tree.get_children()) >= 2, timeout=10)
            self.assertTrue(ok, "DetailDialog file list never filled")
            dlg.destroy()

    def test_emergency_dialog_cancel(self):
        from ui.app import EmergencyDialog
        calls = []
        cands = [{"name": "chrome.exe", "rss": 2_100_000_000, "pid": 4242},
                 {"name": "code.exe", "rss": 900_000_000, "pid": 5151}]
        dlg = EmergencyDialog(self.app, cands, calls.append)
        self.app.update()
        texts = collect_texts(dlg)
        self.assertTrue(any("chrome.exe" in t for t in texts))
        self.assertIsNotNone(dlg.grab_status())
        btn = find_button(dlg, "Cancel")
        self.assertIsNotNone(btn)
        btn.invoke()
        self.assertEqual(calls, [0])
        self.assertFalse(dlg.winfo_exists())

    def test_help_window(self):
        from ui.app import HelpWindow
        dlg = HelpWindow(self.app)
        self.app.update()
        self.assertTrue(dlg.box.get("1.0", "end").strip())
        self.assertIsNotNone(dlg.grab_status())
        dlg.destroy()


if __name__ == "__main__":
    unittest.main()
