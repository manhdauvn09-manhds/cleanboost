"""GUI end-to-end tests (v2.7.0) — real App under a virtual display.

Run with:  xvfb-run -a python -m unittest tests.test_gui_e2e
Skipped automatically when no DISPLAY is available.

These exercise the exact flows the user reported broken on Windows:
an Overview button press must ALWAYS give its button back, a stuck
task must be abandoned at its timeout, the disk scan must find real
junk, the Processes-page kill must kill, and the Top-10 panel fills.
"""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HAS_DISPLAY = bool(os.environ.get("DISPLAY"))


def pump(app, cond, timeout=20.0, step=0.05):
    """Process Tk events until cond() is true or the deadline passes."""
    end = time.time() + timeout
    while time.time() < end:
        app.update()
        if cond():
            return True
        time.sleep(step)
    app.update()
    return cond()


@unittest.skipUnless(HAS_DISPLAY, "needs a display (use xvfb-run)")
class TestGuiE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp_home = tempfile.mkdtemp(prefix="cb-home-")
        cache = Path(cls._tmp_home) / ".cache"
        cache.mkdir(parents=True)
        (cache / "junk1.bin").write_bytes(b"x" * 120_000)
        sub = cache / "sub"
        sub.mkdir()
        (sub / "junk2.bin").write_bytes(b"y" * 60_000)
        # v2.9.0: rules.yaml's lin_home_cache requires min_age_days=1, so
        # freshly-written junk is invisible to the scan. Age it past the
        # threshold or the "scan finds real junk" test scans an empty HOME.
        old = time.time() - 3 * 86400
        for p in (cache / "junk1.bin", sub / "junk2.bin"):
            os.utime(p, (old, old))
        cls._old_home = os.environ.get("HOME")
        os.environ["HOME"] = cls._tmp_home
        from ui.app import App
        cls.app = App()
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        except Exception:
            pass
        if cls._old_home is not None:
            os.environ["HOME"] = cls._old_home

    def test_01_overview_light_button_comes_back(self):
        app = self.app
        import core.memory_cleaner as mc
        orig = mc.light_clean
        mc.light_clean = lambda: ["Standby cache flushed."]
        try:
            app._light()
            ok = pump(app, lambda: "Light clean done" in
                      app.dash_msg.cget("text"), timeout=25)
            self.assertTrue(ok, "light clean result never showed")
            self.assertFalse(app._busy)
            self.assertEqual(str(app.light_btn.cget("state")), "normal")
        finally:
            mc.light_clean = orig

    def test_02_stuck_task_is_abandoned_at_timeout(self):
        app = self.app
        import customtkinter as ctk
        btn = ctk.CTkButton(app, text="probe")
        done_calls = []

        def slow():
            time.sleep(3)
            return "late"

        app._run_bg([btn], slow,
                    done=lambda r: done_calls.append(r),
                    status="Probe slow task", timeout=1)
        t0 = time.time()
        ok = pump(app, lambda: not app._busy, timeout=4)
        self.assertTrue(ok, "busy lock was not released at the timeout")
        self.assertLess(time.time() - t0, 3.0,
                        "lock released only after the task itself ended")
        self.assertEqual(str(btn.cget("state")), "normal")
        self.assertIn("stuck task", app.status_lbl.cget("text"))
        # the stray thread finishes ~2s later; its result must be ignored
        pump(app, lambda: False, timeout=3.5)
        self.assertEqual(done_calls, [])
        self.assertFalse(app._busy)

    def test_03_scan_finds_real_junk(self):
        app = self.app
        app._level.set(1)
        app._scan()
        ok = pump(app, lambda: len(app._scan_checks) > 0, timeout=40)
        self.assertTrue(ok, "scan found nothing in a HOME full of junk")
        total = sum(res["size"] for _v, res in app._scan_checks.values())
        self.assertGreaterEqual(total, 180_000)
        self.assertFalse(app._busy)
        self.assertEqual(str(app.c_scan_btn.cget("state")), "normal")

    def test_04_processes_page_kill_really_kills(self):
        app = self.app
        proc = subprocess.Popen([sys.executable, "-c",
                                 "import time; time.sleep(60)"])
        try:
            from core import process_manager as pm
            app._proc_rows = pm.list_processes(sort_by="memory", limit=300)
            self.assertIn(proc.pid, [r["pid"] for r in app._proc_rows])
            app._fill_proc()
            app.p_tree.selection_set(str(proc.pid))
            app._kill_selected(False)
            ok = pump(app, lambda: proc.poll() is not None, timeout=15)
            self.assertTrue(ok, "selected process is still alive")
            ok = pump(app, lambda: "Closed 1/1" in
                      app.p_msg.cget("text"), timeout=10)
            self.assertTrue(ok, "kill result message never stayed visible")
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_05_top10_panel_fills(self):
        app = self.app
        app._refresh_top()
        ok = pump(app, lambda: "Loading..." not in
                  app.top_ram_box.get("1.0", "end"), timeout=25)
        self.assertTrue(ok, "Top-10 RAM box never filled")
        ram_txt = app.top_ram_box.get("1.0", "end")
        cpu_txt = app.top_cpu_box.get("1.0", "end")
        self.assertIn("PID", ram_txt)
        self.assertIn("PID", cpu_txt)
        self.assertGreaterEqual(len(ram_txt.strip().splitlines()), 3)
        # an auto-refresh may legitimately start right after; wait for
        # the app to settle instead of asserting mid-cycle
        pump(app, lambda: not app._busy, timeout=10)
        self.assertFalse(app._busy)

    def test_06_every_page_opens_and_app_settles(self):
        app = self.app
        for key in ("proc", "clean", "quar", "startup", "net", "dash"):
            app._show_page(key)
            frame, label = app._pages[key]

            def shown(f=frame):
                slaves = app.page_host.pack_slaves()
                if len(slaves) != 1:
                    return False
                # CTkScrollableFrame (dash) reports its inner frame's
                # path, so compare by path prefix, not identity
                return str(f) == str(slaves[0]) or \
                    str(f).startswith(str(slaves[0]) + ".")

            ok = pump(app, shown, timeout=10)
            self.assertTrue(ok, f"page {key} was never packed/shown")
            self.assertEqual(app.page_title.cget("text"), label)
        # after visiting everything (incl. the Network first load), all
        # queued work must drain and release the busy lock
        ok = pump(app, lambda: not app._busy and not app._bg_queue,
                  timeout=120)
        self.assertTrue(ok, "background queue never drained")


class TestSourceHygiene(unittest.TestCase):
    """Static guards for bug patterns the E2E tests caught."""

    def test_no_positional_text_configure(self):
        # widget.configure("some text") silently does nothing on
        # CustomTkinter widgets (the string lands in require_redraw).
        # ttk style.configure("Treeview", ...) and tag_configure are
        # legitimate positional uses and are excluded.
        import ast
        src = (Path(__file__).resolve().parent.parent
               / "ui" / "app.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        bad = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if not (isinstance(f, ast.Attribute) and f.attr == "configure"):
                continue
            recv = f.value
            if isinstance(recv, ast.Name) and recv.id == "style":
                continue
            if node.args:
                bad.append(node.lineno)
        self.assertEqual(bad, [],
                         f"configure() with positional args at lines {bad}")


if __name__ == "__main__":
    unittest.main()
