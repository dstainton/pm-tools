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
