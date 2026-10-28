"""Priority-2 GUI tests (v2.8.0) — buttons that had no GUI test before.

Quarantine ops run against a REAL quarantine in a temp dir (Q.root
patched). DNS / Startup / Diagnostics / Hogs / Adapter / Deep Reset
run with their Windows-only module functions mocked — the GUI flow
(button -> handler -> message) is what is tested here; the Windows
commands themselves are covered by module unit tests and still need
a real Windows run (see the audit report).

Also: the ctypes argtypes hardening (AST check) and the theme-toggle
flip logic (destroy mocked so the fixture survives).

Run with:  xvfb-run -a python -m unittest tests.test_priority2_gui
"""
import ast
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HAS_DISPLAY = bool(os.environ.get("DISPLAY"))


def pump(app, cond, timeout=15, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        app.update()
        if cond():
            return True
        time.sleep(step)
    app.update()
    return cond()


class TestCtpyesHardening(unittest.TestCase):
    """v2.8.0: every Windows foreign call must declare its signature.

    These paths are win32-gated, so on Linux the check is static:
    the assignment must exist in the source.
    """
    CASES = [
        ("core/memory_cleaner.py", "NtSetSystemInformation.argtypes"),
        ("cleaner/clean.py", "SHEmptyRecycleBinW.argtypes"),
        ("cleaner/scanner.py", "SHQueryRecycleBinW.argtypes"),
        ("core/privilege.py", "IsUserAnAdmin.restype"),
    ]

    def test_signatures_declared(self):
        root = Path(__file__).resolve().parent.parent
        for rel, needle in self.CASES:
            src = (root / rel).read_text(encoding="utf-8")
            ast.parse(src)  # must stay valid Python
            self.assertIn(needle, src, f"{rel} is missing {needle}")


@unittest.skipUnless(HAS_DISPLAY, "needs a display (use xvfb-run)")
class TestPriority2Gui(unittest.TestCase):
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

    def setUp(self):
        # Silence every messagebox the handlers may open.
        self._mb = mock.patch("tkinter.messagebox.askyesno",
                              return_value=True)
        self._mb.start()
        self._info = mock.patch("tkinter.messagebox.showinfo")
        self._info.start()
        self._warn = mock.patch("tkinter.messagebox.showwarning")
        self._warn.start()
        self._err = mock.patch("tkinter.messagebox.showerror")
        self._err.start()

    def tearDown(self):
        mock.patch.stopall()

    # ------------------------- Quarantine (real files) -------------------------
    def test_quarantine_restore_delete_purge_select_all(self):
        from cleaner import quarantine as Q
        app = self.app
        with tempfile.TemporaryDirectory() as td:
            qdir = os.path.join(td, "quar")
            orig_dir = os.path.join(td, "orig")
            os.makedirs(orig_dir)
            with mock.patch.object(Q, "root", return_value=qdir):
                app._show_page("quar")
                app.update()
                # Two files in, select-all selects both.
                f1 = os.path.join(orig_dir, "a.txt")
                f2 = os.path.join(orig_dir, "b.txt")
                Path(f1).write_text("aaa")
                Path(f2).write_text("bbb")
                item1 = Q.put(f1, "test")
                item2 = Q.put(f2, "test")
                app._refresh_quarantine()
                app.update()
                self.assertEqual(len(app.q_tree.get_children()), 2)
                app._q_select_all(None)
                app.update()
                self.assertEqual(len(app.q_tree.selection()), 2)
                # Restore f1 by its own id (tree order is by date,
                # newest first — children[0] is NOT necessarily f1).
                app.q_tree.selection_set(item1["id"])
                app._q_restore()
                # The file must really come back to its original path.
                self.assertTrue(pump(app, lambda: os.path.exists(f1),
                                     timeout=10))
                self.assertTrue(pump(app, lambda: len(
                    app.q_tree.get_children()) == 1, timeout=10))
                # Delete the remaining one permanently.
                app.q_tree.selection_set(item2["id"])
                app._q_delete()
                self.assertTrue(pump(app, lambda: len(
                    app.q_tree.get_children()) == 0, timeout=10))
                # Purge removes only expired items.
                f3 = os.path.join(orig_dir, "c.txt")
                Path(f3).write_text("ccc")
                item = Q.put(f3, "test")
                import json
                idx_path = os.path.join(qdir, "index.json")
                idx = json.loads(Path(idx_path).read_text())
                for it in idx["items"]:
                    if it["id"] == item["id"]:
                        it["quarantined_at"] = "2000-01-01T00:00:00+00:00"
                Path(idx_path).write_text(json.dumps(idx))
                app._q_purge()
                self.assertTrue(pump(app, lambda: len(Q.list_items()) == 0,
                                     timeout=10))

    # ------------------------- DNS (mocked Windows calls) -------------------------
    def test_dns_preset_undo_measure(self):
        from network import dns as net_dns
        app = self.app
        app._show_page("net")
        app.update()
        with mock.patch.object(net_dns, "set_dns",
                               return_value=(True, "DNS changed to 1.1.1.1")), \
             mock.patch.object(net_dns, "get_current_dns",
                               return_value=(True, "", {"adapter": "Wi-Fi",
                                                        "dns": ["1.1.1.1"]})):
            app._set_dns_preset("Cloudflare")
            self.assertTrue(pump(app, lambda: "DNS changed"
                                         in app.dns_msg.cget("text")))
        with mock.patch.object(net_dns, "restore_dns",
                               return_value=(True, "DNS restored")), \
             mock.patch.object(net_dns, "get_current_dns",
                               return_value=(True, "", {"adapter": "Wi-Fi",
                                                        "dns": []})):
            app._undo_dns()
            self.assertTrue(pump(app, lambda: "DNS restored"
                                         in app.dns_msg.cget("text")))
        with mock.patch.object(
                net_dns, "measure_dns",
                return_value=(True, "Fastest: Cloudflare",
                              [{"name": "Cloudflare", "ok": True,
                                "avg_ms": 12.0}])):
            app._measure_dns()
            self.assertTrue(pump(app, lambda: "12 ms"
                                         in app.dns_suggest_lbl.cget("text")))

    def test_dns_auto(self):
        from network import dns as net_dns
        app = self.app
        app._show_page("net")
        app.update()
        with mock.patch.object(net_dns, "set_dns_auto",
                               return_value=(True, "DNS set to automatic")), \
             mock.patch.object(net_dns, "get_current_dns",
                               return_value=(True, "", {"adapter": "Wi-Fi",
                                                        "dns": []})):
            app._set_dns_auto_ui()
            self.assertTrue(pump(app, lambda: "automatic"
                                         in app.dns_msg.cget("text")))

    # ------------------------- Startup (mocked registry) -------------------------
    def test_startup_refresh_and_disable(self):
        from core import startup as startup_mod
        app = self.app
        app._show_page("startup")
        app.update()
        entries = [
            {"name": "OneDrive", "key": "OneDrive", "location": "Run",
             "value": r"C:\x\OneDrive.exe", "enabled": True,
             "protected": False},
            {"name": "SecurityHealth", "key": "SecurityHealth",
             "location": "Run", "value": r"C:\x\sec.exe", "enabled": True,
             "protected": True},
        ]
        with mock.patch.object(startup_mod, "list_startup",
                               return_value=(True, "2 entries", entries)):
            app._refresh_startup()
            self.assertTrue(pump(app, lambda: len(
                app.s_tree.get_children()) == 2))
        with mock.patch.object(startup_mod, "set_enabled",
                               return_value=(True, "Disabled OneDrive")), \
             mock.patch.object(startup_mod, "list_startup",
                               return_value=(True, "2 entries", entries)):
            app.s_tree.selection_set("0")
            app._toggle_startup(False)
            self.assertTrue(pump(app, lambda: "Disabled OneDrive"
                                         in app.s_msg.cget("text")))
        # Protected entries are skipped, not disabled.
        with mock.patch.object(startup_mod, "set_enabled") as m_set, \
             mock.patch.object(startup_mod, "list_startup",
                               return_value=(True, "2 entries", entries)):
            app.s_tree.selection_set("1")
            app._toggle_startup(False)
            app.update()
            m_set.assert_not_called()
            self.assertIn("protected", app.s_msg.cget("text"))

    # ------------------------- Diagnostics + Hogs -------------------------
    def test_diagnostics_and_hogs(self):
        from network import diag as net_diag, hogs as net_hogs
        app = self.app
        app._show_page("net")
        app.update()
        with mock.patch.object(net_diag, "run_diagnostics",
                               return_value=(True, "ok", {"ping": "ok"})), \
             mock.patch.object(net_diag, "format_diagnostics",
                               return_value="DIAG FORMATTED"):
            app._run_diagnostics()
            self.assertTrue(pump(app, lambda: "DIAG FORMATTED"
                                         in app.diag_box.get("1.0", "end")))
        hogs_data = {"rows": [{"process": "chrome.exe", "pid": 4242,
                               "connections": 5,
                               "remote_ips": ["1.2.3.4"]}],
                     "recv_per_sec": 2048, "sent_per_sec": 1024}
        import core.process_manager as pm
        with mock.patch.object(net_hogs, "get_bandwidth_hogs",
                               return_value=(True, "1 hog", hogs_data)), \
             mock.patch.object(pm, "kill_process",
                               return_value=(True, "killed")):
            app._find_hogs()
            self.assertTrue(pump(app, lambda: len(
                app.hogs_tree.get_children()) == 1))
            self.assertIn("KB/s down", app.hogs_total_lbl.cget("text"))
            # _end_hog re-runs _find_hogs in its done(), so the hogs
            # mock must stay active across the whole flow.
            app.hogs_tree.selection_set("0")
            app._end_hog()
            self.assertTrue(pump(app, lambda: "Closed 1/1"
                                         in app.hogs_msg.cget("text")))

    # ------------------------- Adapter / Deep Reset prompts -------------------------
    def test_adapter_prompt_cancel_does_not_reset(self):
        from network import refresh as net_refresh
        app = self.app
        app._show_page("net")
        app.update()
        with mock.patch.object(net_refresh, "adapter_reset") as m_reset:
            app._adapter_reset_prompt()
            app.update()
            dlg = next(w for w in app.winfo_children()
                       if w.winfo_class() == "Toplevel"
                       and w.title() == "Adapter Reset")
            import customtkinter as ctk
            stack = list(dlg.winfo_children())
            cancel = None
            while stack:
                x = stack.pop()
                if isinstance(x, ctk.CTkButton) \
                        and x.cget("text") == "Cancel":
                    cancel = x
                    break
                stack.extend(x.winfo_children())
            self.assertIsNotNone(cancel)
            cancel.invoke()
            app.update()
            m_reset.assert_not_called()

    def test_deep_reset_prompt_checkbox_gates_run(self):
        from network import refresh as net_refresh
        app = self.app
        app._show_page("net")
        app.update()
        with mock.patch.object(net_refresh, "deep_reset",
                               return_value=(True, "Deep reset done", [])):
            app._deep_reset_prompt()
            app.update()
            dlg = next(w for w in app.winfo_children()
                       if w.winfo_class() == "Toplevel"
                       and w.title() == "Deep Reset — DANGER")
            import customtkinter as ctk
            stack = list(dlg.winfo_children())
            run_btn = cb = None
            while stack:
                x = stack.pop()
                if isinstance(x, ctk.CTkButton) \
                        and x.cget("text") == "Run Deep Reset":
                    run_btn = x
                if isinstance(x, ctk.CTkCheckBox):
                    cb = x
                stack.extend(x.winfo_children())
            self.assertIsNotNone(run_btn)
            self.assertIsNotNone(cb)
            self.assertEqual(str(run_btn.cget("state")), "disabled")
            # NOTE: CTk's programmatic select() sets the variable but
            # does NOT fire the command (a real mouse click does), so
            # the test fires the command itself after selecting.
            cb.select()
            app.update()
            self.assertTrue(cb.cget("variable").get())
            cb.cget("command")()
            app.update()
            self.assertEqual(str(run_btn.cget("state")), "normal")
            run_btn.invoke()
            self.assertTrue(pump(app, lambda: "Deep reset done"
                                         in app.reset_msg.cget("text")))

    # ------------------------- Theme toggle -------------------------
    def test_theme_toggle_flips(self):
        import customtkinter as ctk
        from ui.app import set_theme
        app = self.app
        before = ctk.get_appearance_mode()  # "Dark" or "Light"
        try:
            with mock.patch.object(app, "destroy"):
                app._toggle_theme()
                m1 = app._next_theme
                self.assertIn(m1, ("light", "dark"))
                app._toggle_theme()
                m2 = app._next_theme
            self.assertIn(m2, ("light", "dark"))
            self.assertNotEqual(m1, m2)
        finally:
            # Leave the shared fixture on its original theme.
            set_theme("dark" if before == "Dark" else "light")
            app._next_theme = None


if __name__ == "__main__":
    unittest.main()
