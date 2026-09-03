import datetime as dt
import unittest

from core import metrics


def issue(key, status="Done", category="done", points=3, transitions=None,
          updated="2026-08-20T09:00:00.000+0000", itype="Story"):
    return {
        "key": key,
        "summary": key,
        "status": status,
        "status_category": category,
        "story_points": points,
        "issuetype": itype,
        "updated": updated,
        "transitions": transitions or [],
    }


def tr(days_ago, frm, to, field="status", today=None):
    today = today or dt.date(2026, 9, 3)
    when = dt.datetime.combine(today - dt.timedelta(days=days_ago),
                               dt.time(9, 0), tzinfo=dt.timezone.utc)
    return {"field": field, "from": frm, "to": to, "when": when, "who": "A"}


class ArithmeticTests(unittest.TestCase):
    def test_cycle_time_and_percentiles(self):
        issues = [
            issue("A", transitions=[tr(20, "To Do", "In Progress"),
                                    tr(10, "In Progress", "Done")]),
            issue("B", transitions=[tr(12, "To Do", "In Progress"),
                                    tr(5, "In Progress", "Done")]),
        ]
        self.assertEqual(metrics.cycle_days(issues[0]), 10)
        self.assertEqual(metrics.cycle_days(issues[1]), 7)
        summary = metrics.cycle_summary(issues)
        self.assertEqual(summary["n"], 2)
        self.assertEqual(summary["median"], 8)
        self.assertEqual(summary["p85"], 10)

    def test_throughput_fills_empty_weeks(self):
        today = dt.date(2026, 9, 3)
        issues = [
            issue("A", transitions=[tr(5, "In Progress", "Done", today=today)]),
            issue("B", transitions=[tr(30, "In Progress", "Done", today=today)]),
        ]
        buckets = metrics.throughput_by_week(issues, weeks=6, today=today)
        self.assertEqual(len(buckets), 6)
        self.assertEqual(sum(b["done"] for b in buckets), 2)
        self.assertTrue(any(b["done"] == 1 for b in buckets))

    def test_landing_date(self):
        today = dt.date(2026, 9, 3)
        when = metrics.landing_date(8, 2.0, today=today)
        self.assertEqual(when, dt.date(2026, 10, 1))
        self.assertIsNone(metrics.landing_date(8, 0, today=today))

    def test_sprint_scope_change(self):
        today = dt.date(2026, 9, 3)
        sprint = {"name": "Sprint 42", "start": "2026-08-27"}
        issues = [
            issue("X", transitions=[
                tr(2, "", "Sprint 42", field="sprint", today=today)]),
            issue("Y", transitions=[
                tr(20, "", "Sprint 42", field="sprint", today=today)]),
        ]
        change = metrics.sprint_scope_change(issues, sprint)
        self.assertEqual(change["added"], 1)
        self.assertEqual(change["keys"], ["X"])
