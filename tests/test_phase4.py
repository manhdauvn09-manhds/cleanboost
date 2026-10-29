"""Phase 4 (automation) tests: auto_clean, scheduler, monitor.

Covers the headless auto-clean script, the weekly schedule
(Task Scheduler / cron) and the RAM/disk monitor loop:
- auto_clean only selects low-risk + default_on rules, includes
  action-specials (size 0 by design, identified by their note),
  and ALWAYS cleans to quarantine — never permanent.
- scheduler install/remove/status on both platforms, including the
  missing-interpreter guard (never write a cron/schtasks line that
  points at a non-existent .venv).
- monitor alerts once per threshold with a 30-min cooldown, and
  logs every alert to the action log.
"""
import os
import sys
import unittest
from contextlib import ExitStack
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auto_clean  # noqa: E402
import main as cli  # noqa: E402
from cleaner import action_log, scheduler  # noqa: E402


def _rule(rid, **kw):
    r = {"id": rid, "name": rid, "level": 1, "os": ["linux", "windows"],
         "risk": "low", "default_on": True, "paths": [], "patterns": ["*"]}
    r.update(kw)
    return r


EMPTY_SUMMARY = {"restore_point": None, "freed_real": 0, "deleted": 0,
                 "quarantined": 0, "quarantined_bytes": 0,
                 "specials": [], "failed": []}


class TestAutoClean(unittest.TestCase):
    def _scan(self, rule, collect_paths=False):
        return {"rule": rule, "size": 777, "count": 1, "samples": [],
                "paths": ["/tmp/junk"]}

    def _run(self, rules, argv, admin=False, scan=None):
        stack = ExitStack()
        stack.enter_context(mock.patch.object(auto_clean.privilege,
                                              "is_admin", return_value=admin))
        stack.enter_context(mock.patch.object(auto_clean.engine, "rules_for",
                                              return_value=rules))
        stack.enter_context(mock.patch.object(auto_clean.scanner, "scan_rule",
                                              side_effect=scan or self._scan))
        log_mock = stack.enter_context(
            mock.patch.object(auto_clean.action_log, "log"))
        clean_mock = stack.enter_context(mock.patch.object(
            auto_clean, "clean_rules", return_value=dict(EMPTY_SUMMARY)))
        stack.enter_context(mock.patch.object(sys, "argv", argv))
        return stack, clean_mock, log_mock

    def test_dry_run_selects_only_low_risk_default_on(self):
        rules = [_rule("safe1"),
                 _rule("risky", risk="high"),
                 _rule("optin", default_on=False),
                 _rule("admin_only", requires_admin=True)]
        stack, clean_mock, log_mock = self._run(rules, ["auto_clean.py", "--dry-run"])
        with stack:
            auto_clean.main()
        clean_mock.assert_not_called()

    def test_real_mode_cleans_selected_ids_to_quarantine(self):
        rules = [_rule("safe1"), _rule("risky", risk="high")]
        stack, clean_mock, log_mock = self._run(rules, ["auto_clean.py"])
        with stack:
            auto_clean.main()
        clean_mock.assert_called_once()
        self.assertEqual(clean_mock.call_args.args[1], {"safe1"})
        self.assertIs(clean_mock.call_args.kwargs["permanent"], False)

    def test_admin_rule_included_when_root(self):
        rules = [_rule("admin_only", requires_admin=True)]
        stack, clean_mock, log_mock = self._run(rules, ["auto_clean.py"], admin=True)
        with stack:
            auto_clean.main()
        clean_mock.assert_called_once()
        self.assertEqual(clean_mock.call_args.args[1], {"admin_only"})

    def test_action_special_with_note_is_selected(self):
        # Bug #3 fix: action-specials have size 0 by design (they run a
        # command) — they must be selected via their note, not their size.
        rules = [_rule("dism", special="dism_cleanup",
                       note="Runs DISM component cleanup")]

        def scan(rule, collect_paths=False):
            return {"rule": rule, "size": 0, "count": 0, "samples": [],
                    "paths": [], "note": rule.get("note")}

        stack, clean_mock, log_mock = self._run(rules, ["auto_clean.py"], admin=True,
                                      scan=scan)
        with stack:
            auto_clean.main()
        clean_mock.assert_called_once()
        self.assertEqual(clean_mock.call_args.args[1], {"dism"})

    def test_nothing_to_clean_never_calls_clean(self):
        rules = [_rule("risky", risk="high")]
        stack, clean_mock, log_mock = self._run(rules, ["auto_clean.py"])
        with stack:
            auto_clean.main()
        clean_mock.assert_not_called()

    def test_dry_run_logs_scan_event(self):
        rules = [_rule("safe1")]
        stack, _clean_mock, log_mock = self._run(rules,
                                                ["auto_clean.py", "--dry-run"])
        with stack:
            auto_clean.main()
        log_mock.assert_called_once()
        self.assertEqual(log_mock.call_args.args[0], "auto_clean_scan")
        self.assertTrue(log_mock.call_args.args[1]["dry_run"])


class TestSchedulerLinux(unittest.TestCase):
    def _linux(self):
        return mock.patch.object(sys, "platform", "linux")

    def _venv_ok(self):
        return mock.patch("os.path.exists", return_value=True)

    def test_install_writes_cron_line(self):
        calls = []

        def fake_run(argv, input=None, **kw):
            calls.append((list(argv), input))
            if argv == ["crontab", "-l"]:
                return mock.Mock(returncode=1, stdout="", stderr="")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with self._linux(), self._venv_ok(), \
                mock.patch.object(scheduler.subprocess, "run",
                                  side_effect=fake_run):
            ok, msg = scheduler.install()
        self.assertTrue(ok)
        self.assertEqual(len(calls), 2)
        self.assertIn("0 3 * * 0", calls[-1][1])
        self.assertIn("auto_clean.py", calls[-1][1])

    def test_install_skips_when_already_registered(self):
        existing = ("# my crons\n"
                    "0 3 * * 0 /x/auto_clean.py >> /x/auto_clean.log 2>&1\n")
        calls = []

        def fake_run(argv, input=None, **kw):
            calls.append((list(argv), input))
            if argv == ["crontab", "-l"]:
                return mock.Mock(returncode=0, stdout=existing, stderr="")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with self._linux(), self._venv_ok(), \
                mock.patch.object(scheduler.subprocess, "run",
                                  side_effect=fake_run):
            ok, msg = scheduler.install()
        self.assertTrue(ok)
        self.assertIn("already", msg.lower())
        self.assertEqual(len(calls), 1)  # never wrote

    def test_install_refuses_without_venv(self):
        # Bug #8 fix: never write a cron line pointing at a missing
        # interpreter — the weekly job would silently fail.
        with self._linux(), mock.patch("os.path.exists", return_value=False):
            ok, msg = scheduler.install()
        self.assertFalse(ok)
        self.assertIn(".venv", msg)

    def test_remove_strips_only_auto_clean_line(self):
        existing = ("0 3 * * 0 /x/auto_clean.py >> /x/auto_clean.log 2>&1\n"
                    "0 9 * * * /other/job\n")
        calls = []

        def fake_run(argv, input=None, **kw):
            calls.append((list(argv), input))
            if argv == ["crontab", "-l"]:
                return mock.Mock(returncode=0, stdout=existing, stderr="")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with self._linux(), mock.patch.object(scheduler.subprocess, "run",
                                              side_effect=fake_run):
            ok, msg = scheduler.remove()
        self.assertTrue(ok)
        self.assertNotIn("auto_clean.py", calls[-1][1])
        self.assertIn("/other/job", calls[-1][1])

    def test_status_detects_registered(self):
        with self._linux(), mock.patch.object(
                scheduler.subprocess, "run",
                return_value=mock.Mock(returncode=0,
                                       stdout="0 3 * * 0 /x/auto_clean.py",
                                       stderr="")):
            ok, msg = scheduler.status()
        self.assertTrue(ok)
        self.assertIn("scheduled", msg.lower())

    def test_status_detects_not_registered(self):
        with self._linux(), mock.patch.object(
                scheduler.subprocess, "run",
                return_value=mock.Mock(returncode=0, stdout="# nothing here",
                                       stderr="")):
            ok, msg = scheduler.status()
        self.assertFalse(ok)


class TestSchedulerWindows(unittest.TestCase):
    def _win(self):
        return mock.patch.object(sys, "platform", "win32")

    def test_install_builds_schtasks_command(self):
        with self._win(), \
                mock.patch.object(scheduler.privilege, "is_admin",
                                  return_value=True), \
                mock.patch("os.path.exists", return_value=True), \
                mock.patch.object(scheduler.subprocess, "run") as run_mock:
            run_mock.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            ok, msg = scheduler.install()
        self.assertTrue(ok)
        cmd = run_mock.call_args.args[0]
        self.assertEqual(cmd[0], "schtasks")
        self.assertIn("/SC", cmd)
        self.assertIn("/D", cmd)
        self.assertIn("SUN", cmd)
        self.assertIn("/RL", cmd)
        self.assertIn("HIGHEST", cmd)

    def test_install_without_admin_omits_highest_flag(self):
        with self._win(), \
                mock.patch.object(scheduler.privilege, "is_admin",
                                  return_value=False), \
                mock.patch("os.path.exists", return_value=True), \
                mock.patch.object(scheduler.subprocess, "run") as run_mock:
            run_mock.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            ok, msg = scheduler.install()
        self.assertTrue(ok)
        self.assertIn("Admin", msg)
        cmd = run_mock.call_args.args[0]
        self.assertNotIn("/RL", cmd)

    def test_install_refuses_without_venv(self):
        with self._win(), mock.patch("os.path.exists", return_value=False):
            ok, msg = scheduler.install()
        self.assertFalse(ok)
        self.assertIn(".venv", msg)

    def test_status_windows_registered(self):
        with self._win(), mock.patch.object(
                scheduler.subprocess, "run",
                return_value=mock.Mock(returncode=0, stdout="INFO", stderr="")):
            ok, msg = scheduler.status()
        self.assertTrue(ok)
        self.assertIn("Registered", msg)

    def test_remove_windows_success(self):
        with self._win(), mock.patch.object(
                scheduler.subprocess, "run",
                return_value=mock.Mock(returncode=0, stdout="", stderr="")):
            ok, msg = scheduler.remove()
        self.assertTrue(ok)

    def test_remove_windows_not_found(self):
        with self._win(), mock.patch.object(
                scheduler.subprocess, "run",
                return_value=mock.Mock(returncode=1, stdout="", stderr="")):
            ok, msg = scheduler.remove()
        self.assertFalse(ok)


class TestCmdSchedule(unittest.TestCase):
    def test_status_prints_message(self):
        with mock.patch.object(scheduler, "status",
                               return_value=(True, "Registered: X")), \
                mock.patch("builtins.print") as print_mock:
            cli.cmd_schedule(mock.Mock(scmd="status"))
        print_mock.assert_called_once_with("Registered: X")

    def test_install_prints_failure(self):
        with mock.patch.object(scheduler, "install",
                               return_value=(False, "No .venv yet")), \
                mock.patch("builtins.print") as print_mock:
            cli.cmd_schedule(mock.Mock(scmd="install"))
        print_mock.assert_called_once_with("No .venv yet")


class TestMonitor(unittest.TestCase):
    def _args(self, **kw):
        base = dict(interval=1, ram=90, disk_free=10)
        base.update(kw)
        return mock.Mock(**base)

    def _mem(self, percent):
        return {"total": 8192, "available": 8192 * (100 - percent) / 100,
                "used": 8192 * percent / 100, "percent": percent}

    def _disk(self, percent):
        return {"total": 524288, "used": 524288 * percent / 100,
                "free": 524288 * (100 - percent) / 100, "percent": percent}

    def _patches(self, mem, disk):
        stack = ExitStack()
        stack.enter_context(mock.patch.object(cli.system_info, "memory",
                                              return_value=mem))
        stack.enter_context(mock.patch.object(cli.system_info, "disk",
                                              return_value=disk))
        popup_mock = stack.enter_context(mock.patch.object(cli, "_notify_popup"))
        log_mock = stack.enter_context(mock.patch.object(action_log, "log"))
        stack.enter_context(mock.patch("time.sleep",
                                       side_effect=KeyboardInterrupt))
        return stack, popup_mock, log_mock

    def test_alerts_on_high_ram_and_low_disk(self):
        stack, popup_mock, log_mock = self._patches(self._mem(95),
                                                    self._disk(95))
        with stack:
            cli.cmd_monitor(self._args())
        msgs = [c.args[0] for c in popup_mock.call_args_list]
        self.assertTrue(any("RAM" in m for m in msgs), msgs)
        self.assertTrue(any("drive" in m for m in msgs), msgs)
        types = [c.args[1]["type"] for c in log_mock.call_args_list
                 if c.args[0] == "monitor_alert"]
        self.assertIn("ram", types)
        self.assertIn("disk", types)

    def test_no_alert_when_healthy(self):
        stack, popup_mock, log_mock = self._patches(self._mem(40),
                                                    self._disk(50))
        with stack:
            cli.cmd_monitor(self._args())
        popup_mock.assert_not_called()
        log_mock.assert_not_called()

    def test_cooldown_blocks_repeat_alert(self):
        sleeps = iter([None, KeyboardInterrupt])

        def fake_sleep(_seconds):
            event = next(sleeps)
            if event is not None:
                raise event

        stack = ExitStack()
        stack.enter_context(mock.patch.object(cli.system_info, "memory",
                                              return_value=self._mem(95)))
        stack.enter_context(mock.patch.object(cli.system_info, "disk",
                                              return_value=self._disk(50)))
        popup_mock = stack.enter_context(mock.patch.object(cli, "_notify_popup"))
        log_mock = stack.enter_context(mock.patch.object(action_log, "log"))
        stack.enter_context(mock.patch("time.sleep", side_effect=fake_sleep))
        with stack:
            cli.cmd_monitor(self._args())
        self.assertEqual(popup_mock.call_count, 1)
        self.assertEqual(log_mock.call_count, 1)

    def test_ram_threshold_not_crossed_no_ram_alert(self):
        stack, popup_mock, _log_mock = self._patches(self._mem(85),
                                                     self._disk(95))
        with stack:
            cli.cmd_monitor(self._args())
        msgs = [c.args[0] for c in popup_mock.call_args_list]
        self.assertFalse(any("RAM" in m for m in msgs), msgs)
        self.assertTrue(any("drive" in m for m in msgs), msgs)


if __name__ == "__main__":
    unittest.main()