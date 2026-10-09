"""Fiscal year, quarter, landing text, and the no-inference wording."""

import datetime as dt
import unittest

from commands import daily, lint, metrics as metrics_cmd
from core import config, fiscal, metrics


class FiscalYearTests(unittest.TestCase):
    def test_the_fiscal_year_is_the_year_of_the_next_year_end(self):
        self.assertEqual(fiscal.fiscal_year(dt.date(2026, 10, 9), "03-31"), 2027)
        period = fiscal.period_containing(dt.date(2026, 10, 9), "03-31")
        self.assertEqual(period["quarter"], 3)
        self.assertEqual(period["start"], dt.date(2026, 10, 1))
        self.assertEqual(period["end"], dt.date(2026, 12, 31))

    def test_quarter_one_starts_the_day_after_year_end(self):
        periods = fiscal.quarters(2027, "03-31")
        self.assertEqual(
            [(p["start"], p["end"]) for p in periods],
            [
                (dt.date(2026, 4, 1), dt.date(2026, 6, 30)),
                (dt.date(2026, 7, 1), dt.date(2026, 9, 30)),
                (dt.date(2026, 10, 1), dt.date(2026, 12, 31)),
                (dt.date(2027, 1, 1), dt.date(2027, 3, 31)),
            ])

    def test_the_year_end_day_is_still_that_fiscal_year(self):
        self.assertEqual(fiscal.fiscal_year(dt.date(2027, 3, 31), "03-31"), 2027)
        self.assertEqual(
            fiscal.period_containing(dt.date(2027, 3, 31), "03-31")["quarter"], 4)
        self.assertEqual(fiscal.fiscal_year(dt.date(2027, 4, 1), "03-31"), 2028)
        opened = fiscal.period_containing(dt.date(2027, 4, 1), "03-31")
        self.assertEqual(opened["year"], 2028)
        self.assertEqual(opened["quarter"], 1)
        self.assertEqual(opened["start"], dt.date(2027, 4, 1))

    def test_a_january_year_end_still_uses_three_calendar_months(self):
        periods = fiscal.quarters(2027, "01-31")
        self.assertEqual(periods[0]["start"], dt.date(2026, 2, 1))
        self.assertEqual(periods[0]["end"], dt.date(2026, 4, 30))
        self.assertEqual(periods[3]["end"], dt.date(2027, 1, 31))

    def test_february_29_clamps_when_the_year_is_not_a_leap_year(self):
        self.assertEqual(fiscal.year_end_date(2027, "02-29"), dt.date(2027, 2, 28))
        self.assertEqual(fiscal.year_end_date(2028, "02-29"), dt.date(2028, 2, 29))

    def test_a_bad_year_end_is_rejected(self):
        with self.assertRaises(SystemExit):
            config._validate_metrics({"metrics": {"year_end": "03-32"}})
        self.assertEqual(fiscal.canonical("3-31"), "03-31")


class ReportTextTests(unittest.TestCase):
    def _groups(self, landing):
        today = dt.date(2026, 10, 9)
        start = metrics.week_start(today) - dt.timedelta(weeks=7)
        buckets = []
        for i in range(8):
            week = start + dt.timedelta(weeks=i)
            buckets.append({
                "week": metrics.iso_week(week),
                "start": week.isoformat(),
                "end": (week + dt.timedelta(days=6)).isoformat(),
                "done": 2,
                "points": 5,
            })
        row = {
            "workstream": "SDX",
            "throughput": buckets,
            "weekly_rate": 2.0,
            "weekly_points": 5.0,
            "cycle": {"n": 4, "median": 6, "p85": 10},
            "open": 8,
            "open_points": 21,
            "landing": landing,
            "scope_change": {"added": 1},
            "accuracy": {"done": 10, "forecast": 16},
            "aging": [],
        }
        return today, [({"name": "Integration Platform", "abbrev": "IP"}, [row])]

    def test_the_report_names_points_fiscal_quarter_and_a_landing_range(self):
        today, groups = self._groups({
            "early": dt.date(2026, 10, 23),
            "late": dt.date(2026, 11, 20),
            "mid": dt.date(2026, 11, 6),
            "open_ended": False,
        })
        text = metrics_cmd.render(groups, 8, year_end="03-31", today=today)
        self.assertIn("no inference model used", text)
        self.assertNotIn("no model", text)
        self.assertIn("FY2027 ends 31 Mar 2027", text)
        self.assertIn("FY2027 Q3 (1 Oct – 31 Dec 2026)", text)
        self.assertIn("FY2027 Q2–Q3", text)
        self.assertIn("Points / week", text)
        self.assertIn("Open pts", text)
        self.assertIn("5.0", text)
        self.assertIn("21", text)
        self.assertIn("23 Oct – 20 Nov (FY2027 Q3)", text)
        self.assertIn("SDX pts", text)
        self.assertIn("FY2027 Q2", text)

    def test_an_unbounded_landing_says_or_later(self):
        today, groups = self._groups({
            "early": dt.date(2026, 10, 16),
            "late": None,
            "mid": dt.date(2026, 11, 6),
            "open_ended": True,
        })
        text = metrics_cmd.render(groups, 8, year_end="03-31", today=today)
        self.assertIn("16 Oct or later (FY2027 Q3)", text)

    def test_daily_and_lint_say_no_inference_model_used(self):
        daily_text = daily.build_markdown({}, [], 1, "workstream")
        self.assertIn("no inference model used", daily_text)
        self.assertNotIn("no model.", daily_text)
        lint_text = lint.build_markdown({}, [])
        self.assertIn("No inference model used", lint_text)
        self.assertNotIn("No model involved", lint_text)


if __name__ == "__main__":
    unittest.main()
