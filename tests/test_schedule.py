import os
import tempfile
import unittest

from commands import schedule


class ParseWhenTests(unittest.TestCase):
    def test_weekdays_at(self):
        when = schedule.parse_when(at="08:30")
        self.assertEqual(when["kind"], "weekdays")
        self.assertEqual(when["time"], "08:30")
        self.assertEqual(len(when["days"]), 5)

    def test_weekly(self):
        when = schedule.parse_when(weekly="fri@16:00")
        self.assertEqual(when["kind"], "weekly")
        self.assertEqual(when["days"], ["fri"])
        self.assertEqual(when["time"], "16:00")

    def test_bad_weekly_raises(self):
        with self.assertRaises(ValueError):
            schedule.parse_when(weekly="friday 4pm")


class CronTests(unittest.TestCase):
    def test_weekday_line(self):
        job = {"command": "today", "args": [], "kind": "weekdays",
               "days": ["mon", "tue", "wed", "thu", "fri"], "time": "08:30"}
        self.assertEqual(schedule.cron_line(job), "30 8 * * 1-5 pm today")

    def test_friday_report(self):
        job = {"command": "report", "args": ["--product", "IP"],
               "kind": "weekly", "days": ["fri"], "time": "16:00"}
        self.assertEqual(schedule.cron_line(job),
                         "0 16 * * 5 pm report --product IP")


class StoreTests(unittest.TestCase):
    def test_add_then_remove(self):
        folder = tempfile.mkdtemp(prefix="pm-sched-")
        cfg = {"state": {"local_path": folder, "shared_path": folder}}
        from argparse import Namespace
        schedule._add(cfg, Namespace(
            target="today", at="08:30", weekly=None,
            for_audience=None, product=None, workstream=None))
        store = schedule._store(cfg)
        self.assertEqual(store["jobs"][0]["command"], "today")
        self.assertTrue(os.path.exists(os.path.join(folder, "schedule.cron")))
        schedule._remove(cfg, Namespace(target="today"))
        self.assertEqual(schedule._store(cfg)["jobs"], [])


class WindowsRegistrationTests(unittest.TestCase):
    JOB = {"name": "today", "command": "today", "args": [], "kind": "weekdays",
           "days": ["mon", "tue", "wed", "thu", "fri"], "time": "08:30"}

    def test_script_ships_inside_the_commands_package(self):
        self.assertTrue(os.path.isfile(schedule.REGISTER_SCRIPT))
        self.assertEqual(os.path.dirname(schedule.REGISTER_SCRIPT),
                         os.path.dirname(os.path.abspath(schedule.__file__)))

    def test_missing_script_is_reported(self):
        from unittest import mock
        with mock.patch.object(schedule, "REGISTER_SCRIPT", "/nowhere/x.ps1"):
            problem = schedule._register_windows(self.JOB)
        self.assertIn("missing", problem)

    def test_failed_powershell_is_reported(self):
        from unittest import mock
        import subprocess
        failed = subprocess.CompletedProcess([], 1, stdout="",
                                             stderr="Access is denied.\n")
        with mock.patch.object(schedule.subprocess, "run", return_value=failed):
            self.assertEqual(schedule._register_windows(self.JOB), "Access is denied.")

    def test_success_returns_none(self):
        from unittest import mock
        import subprocess
        ok = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        with mock.patch.object(schedule.subprocess, "run", return_value=ok) as run:
            self.assertIsNone(schedule._register_windows(self.JOB))
        self.assertIn(schedule.REGISTER_SCRIPT, run.call_args[0][0])

    def test_add_on_windows_says_when_registration_failed(self):
        import io
        from argparse import Namespace
        from contextlib import redirect_stdout
        from unittest import mock
        folder = tempfile.mkdtemp(prefix="pm-sched-")
        cfg = {"state": {"local_path": folder, "shared_path": folder}}
        out = io.StringIO()
        with mock.patch.object(schedule.os, "name", "nt"), \
                mock.patch.object(schedule, "_register_windows", return_value="Access is denied."), \
                redirect_stdout(out):
            schedule._add(cfg, Namespace(
                target="today", at="08:30", weekly=None,
                for_audience=None, product=None, workstream=None))
        self.assertIn("Not registered with Task Scheduler: Access is denied.", out.getvalue())
        self.assertNotIn("Registered with Task Scheduler.", out.getvalue())

    def test_arguments_with_spaces_are_quoted_for_windows(self):
        from unittest import mock
        import subprocess
        ok = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        job = dict(self.JOB, name="brief", command="brief",
                   args=["--for", "Leadership team"])
        with mock.patch.object(schedule.subprocess, "run", return_value=ok) as run:
            schedule._register_windows(job)
        argv = run.call_args[0][0]
        self.assertEqual(argv[argv.index("-Command") + 1], 'brief --for "Leadership team"')

    def test_remove_on_windows_deletes_the_task(self):
        import io
        import subprocess
        from argparse import Namespace
        from contextlib import redirect_stdout
        from unittest import mock
        folder = tempfile.mkdtemp(prefix="pm-sched-")
        cfg = {"state": {"local_path": folder, "shared_path": folder}}
        schedule._save(cfg, {"jobs": [dict(self.JOB)]})
        ok = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        out = io.StringIO()
        with mock.patch.object(schedule.os, "name", "nt"), \
                mock.patch.object(schedule.subprocess, "run", return_value=ok) as run, \
                redirect_stdout(out):
            schedule._remove(cfg, Namespace(target="today"))
        self.assertEqual(run.call_args[0][0], ["schtasks", "/Delete", "/TN", "\\pm\\today", "/F"])
        self.assertIn("Removed Task Scheduler entry", out.getvalue())
