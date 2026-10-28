"""Kill-flow tests (v2.8.0) — the OneDrive force-kill report.

Covers: friendly app names, the ForceKillDialog (names its targets),
kill verification (gone / alive / respawned), the AccessDenied path,
no-selection feedback, queued-task visibility, and re-selection of
respawned rows after refresh.

Run with:  xvfb-run -a python -m unittest tests.test_kill_flow
Skipped automatically when no DISPLAY is available (GUI parts only).
"""
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HAS_DISPLAY = bool(os.environ.get("DISPLAY"))


class TestFriendlyNames(unittest.TestCase):
    def test_map_and_fallback(self):
        from ui.app import friendly_app_name as f
        self.assertEqual(f("OneDrive.exe"), "OneDrive")
        self.assertEqual(f("ONEDRIVE.EXE"), "OneDrive")
        self.assertEqual(f("chrome.exe"), "Google Chrome")
        self.assertEqual(f("code.exe"), "Visual Studio Code")
        self.assertEqual(f("my_cool-app.exe"), "My Cool App")
        self.assertEqual(f("sleep"), "Sleep")
        self.assertEqual(f(""), "Unknown app")


class TestVerifyGone(unittest.TestCase):
    def test_gone(self):
        from core.process_manager import verify_process_gone, \
            snapshot_pids_by_name
        p = subprocess.Popen(["sleep", "30"])
        # Snapshot BEFORE the kill: unrelated system sleeps (if any)
        # must not count as a respawn of this victim.
        known = snapshot_pids_by_name("sleep")
        p.kill()
        p.wait()
        self.assertEqual(verify_process_gone(p.pid, "sleep",
                                             known_pids=known),
                         ("gone", None))

    def test_alive(self):
        from core.process_manager import verify_process_gone
        p = subprocess.Popen(["sleep", "30"])
        try:
            self.assertEqual(
                verify_process_gone(p.pid, "sleep",
                                    known_pids={p.pid}, timeout=0.5),
                ("alive", None))
        finally:
            p.kill()
            p.wait()

    def test_respawned(self):
        from core.process_manager import verify_process_gone, \
            snapshot_pids_by_name
        victim = subprocess.Popen(["sleep", "30"])
        known = snapshot_pids_by_name("sleep")
        victim.kill()
        victim.wait()
        # A same-name process NOT in the pre-kill snapshot is a respawn.
        respawn = subprocess.Popen(["sleep", "30"])
        try:
            state, new_pid = verify_process_gone(victim.pid, "sleep",
                                                 known_pids=known)
            self.assertEqual(state, "respawned")
            self.assertEqual(new_pid, respawn.pid)
        finally:
            respawn.kill()
            respawn.wait()

    def test_preexisting_instance_is_not_respawn(self):
        from core.process_manager import verify_process_gone, \
            snapshot_pids_by_name
        other = subprocess.Popen(["sleep", "30"])
        victim = subprocess.Popen(["sleep", "30"])
        try:
            known = snapshot_pids_by_name("sleep")
            victim.kill()
            victim.wait()
            # `other` was in the pre-kill snapshot, so it must NOT count.
            self.assertEqual(verify_process_gone(victim.pid, "sleep",
                                                 known_pids=known),
                             ("gone", None))
        finally:
            other.kill()
            other.wait()


def pump(app, cond, timeout=15, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        app.update()
        if cond():
            return True
        time.sleep(step)
    app.update()
    return cond()


def auto_confirm_force_kill(app, tries=100):
    """Dismiss the ForceKillDialog by clicking its Force kill button.

    The dialog is modal (wait_window runs its own event loop), so an
    after() callback fires while _kill_selected is blocked in it.
    Stops polling after ~10s so a test that never opens the dialog
    does not leave a live after-chain behind.
    """
    import customtkinter as ctk

    def dismiss(left):
        try:
            children = app.winfo_children()
        except Exception:
            return
        for w in children:
            if w.winfo_class() == "Toplevel" and w.title() == "Force kill":
                stack = list(w.winfo_children())
                while stack:
                    x = stack.pop()
                    try:
                        if isinstance(x, ctk.CTkButton) \
                                and x.cget("text") == "Force kill":
                            x.invoke()
                            return
                    except Exception:
                        pass
                    stack.extend(x.winfo_children())
                return
        if left > 0:
            try:
                app.after(100, lambda: dismiss(left - 1))
            except Exception:
                pass

    app.after(100, lambda: dismiss(tries))


@unittest.skipUnless(HAS_DISPLAY, "needs a display (use xvfb-run)")
class TestForceKillDialog(unittest.TestCase):
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

    def _targets(self):
        return [
            {"pid": 1111, "name": "OneDrive.exe", "rss": 400_000_000,
             "warn": False},
            {"pid": 2222, "name": "explorer.exe", "rss": 100_000_000,
             "warn": True},
        ]

    def test_dialog_names_targets_and_is_modal(self):
        from ui.app import ForceKillDialog
        dlg = ForceKillDialog(self.app, self._targets())
        self.app.update()
        texts = []

        def walk(w):
            try:
                t = w.cget("text")
                if isinstance(t, str) and t:
                    texts.append(t)
            except Exception:
                pass
            for c in w.winfo_children():
                walk(c)
        walk(dlg)
        self.assertIn("OneDrive", texts)
        self.assertTrue(any("OneDrive.exe" in t and "PID 1111" in t
                            for t in texts))
        self.assertTrue(any("Sensitive system process" in t for t in texts))
        self.assertIsNotNone(dlg.grab_status())
        dlg._no()
        self.assertFalse(dlg.result)

    def test_dialog_yes_path(self):
        from ui.app import ForceKillDialog
        dlg = ForceKillDialog(self.app, self._targets())
        self.app.update()
        dlg._yes()
        self.assertTrue(dlg.result)


@unittest.skipUnless(HAS_DISPLAY, "needs a display (use xvfb-run)")
class TestKillFlowGui(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ui.app import App
        cls.app = App()
        cls.app.deiconify()
        cls.app.update()
        cls.app._show_page("proc")
        cls.app.update()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        except Exception:
            pass

    def _select_pid(self, pid):
        self.app._refresh_proc()
        self.assertTrue(pump(self.app, lambda: any(
            r["pid"] == pid for r in self.app._proc_rows)),
            "process not listed")
        self.app.p_tree.selection_set(str(pid))
        self.app.update()

    def test_no_selection_feedback(self):
        app = self.app
        app.p_tree.selection_remove(app.p_tree.selection())
        app.update()
        app._kill_selected(True)
        app.update()
        self.assertIn("No process selected", app.p_msg.cget("text"))
        self.assertIn("No process selected", app.status_lbl.cget("text"))

    def test_real_force_kill_then_buttons_back(self):
        app = self.app
        victim = subprocess.Popen(["sleep", "300"])
        try:
            self._select_pid(victim.pid)
            auto_confirm_force_kill(app)
            app._kill_selected(True)
            self.assertTrue(pump(app, lambda: victim.poll() is not None))
            self.assertTrue(pump(app, lambda: str(
                app.p_fkill_btn.cget("state")) == "normal"))
            self.assertIn("Closed 1/1", app.p_msg.cget("text"))
        finally:
            if victim.poll() is None:
                victim.kill()

    def test_access_denied_message_and_buttons_back(self):
        import core.process_manager as pm
        app = self.app
        victim = subprocess.Popen(["sleep", "300"])
        try:
            self._select_pid(victim.pid)
            auto_confirm_force_kill(app)
            # Keep the mock alive until the task finishes (the worker
            # runs after _kill_selected returns).
            patcher = mock.patch.object(
                pm, "kill_process",
                return_value=(False, "Access denied — run the app as Admin "
                                     "(Windows) / sudo (Linux) and try again."))
            patcher.start()
            try:
                app._kill_selected(True)
                self.assertTrue(pump(app, lambda: "Could not close"
                                         in app.p_msg.cget("text")))
            finally:
                patcher.stop()
            self.assertIn("run_cleanboost_admin.bat",
                          app.p_msg.cget("text"))
            self.assertEqual(str(app.p_fkill_btn.cget("state")), "normal")
            # The mocked kill never ran, so the victim must be alive.
            self.assertIsNone(victim.poll())
        finally:
            if victim.poll() is None:
                victim.kill()

    def test_respawn_reported_and_row_reselected(self):
        import core.process_manager as pm
        app = self.app
        victim = subprocess.Popen(["sleep", "300"])
        spawned = []
        real_kill = pm.kill_process

        def killing_kill(pid, force=False):
            ok, msg = real_kill(pid, force=force)
            if ok:
                # Simulate OneDrive-style self-restart: a new process
                # with the same name appears right after the kill.
                spawned.append(subprocess.Popen(["sleep", "300"]))
            return ok, msg

        try:
            self._select_pid(victim.pid)
            auto_confirm_force_kill(app)
            patcher = mock.patch.object(pm, "kill_process",
                                        side_effect=killing_kill)
            patcher.start()
            try:
                app._kill_selected(True)
                self.assertTrue(pump(app, lambda: "restarted itself"
                                         in app.p_msg.cget("text"),
                                     timeout=20))
            finally:
                patcher.stop()
            # The respawned row (by its NEW pid) is re-selected so
            # retrying is one click.
            self.assertTrue(pump(app, lambda: str(spawned[0].pid)
                                         in app.p_tree.selection()),
                            "respawned row not re-selected")
        finally:
            if victim.poll() is None:
                victim.kill()
            for p in spawned:
                if p.poll() is None:
                    p.kill()

    def test_queued_kill_shows_queued_status(self):
        import threading
        app = self.app
        started = threading.Event()
        release = threading.Event()

        def slow_work():
            started.set()
            release.wait(30)
            return "slow done"

        app._run_bg([app.p_refresh_btn], slow_work, done=lambda r: None,
                     status="Slow dummy task...")
        # Pump the event loop while waiting: _bg_poll/_finish_bg run
        # on the UI thread, so a bare started.wait() would starve the
        # very task that starts the slow worker.
        self.assertTrue(pump(app, lambda: started.is_set(), timeout=10))
        victim = subprocess.Popen(["sleep", "300"])
        try:
            # Inject the row directly: a real _refresh_proc here would
            # itself queue behind the slow task and drain first,
            # defeating the point of this test.
            app._proc_rows.append({"pid": victim.pid, "name": "sleep",
                                   "rss": 1000, "cpu": 0.0, "user": "root",
                                   "mine": True, "state": "ok"})
            app.p_tree.insert("", "end", iid=str(victim.pid),
                              text=str(victim.pid),
                              values=("0.0 GB", "0.0", "root", "sleep"))
            app.p_tree.selection_set(str(victim.pid))
            app.update()
            auto_confirm_force_kill(app)
            app._kill_selected(True)
            app.update()
            # The click is queued (button disabled) AND the status bar
            # says so — the old "button just died" experience is gone.
            self.assertEqual(len(app._bg_queue), 1)
            self.assertIn("Queued", app.status_lbl.cget("text"))
            release.set()
            self.assertTrue(pump(app, lambda: victim.poll() is not None,
                                 timeout=20))
            # The victim dies in the worker; the button comes back a
            # tick later when _finish_bg runs — pump for that too.
            self.assertTrue(pump(app, lambda: str(
                app.p_fkill_btn.cget("state")) == "normal"))
        finally:
            release.set()
            if victim.poll() is None:
                victim.kill()


if __name__ == "__main__":
    unittest.main()
