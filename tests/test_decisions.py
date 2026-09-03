import datetime as dt
import os
import tempfile
import unittest

from core import decisions


class ParseUntilTests(unittest.TestCase):
    def test_iso_date(self):
        self.assertEqual(decisions.parse_until("2026-09-17"), "2026-09-17")

    def test_relative_days_and_weeks(self):
        today = dt.date(2026, 9, 3)
        self.assertEqual(decisions.parse_until("14d", today=today), "2026-09-17")
        self.assertEqual(decisions.parse_until("2w", today=today), "2026-09-17")

    def test_next_sprint_uses_end_date(self):
        today = dt.date(2026, 9, 3)
        self.assertEqual(
            decisions.parse_until("next-sprint", today=today,
                                  sprint_end="2026-09-10"),
            "2026-09-10")
        self.assertEqual(
            decisions.parse_until("next-sprint", today=today),
            "2026-09-17")

    def test_bad_value_raises(self):
        with self.assertRaises(ValueError):
            decisions.parse_until("soon")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="pm-decisions-")
        self.cfg = {"state": {"shared_path": self.dir, "local_path": self.dir}}

    def tearDown(self):
        for name in os.listdir(self.dir):
            os.remove(os.path.join(self.dir, name))
        os.rmdir(self.dir)

    def test_snooze_hides_until_expiry(self):
        decisions.record(self.cfg, "snooze", "APS-11", "cosmetic",
                         until="2026-09-17", today=dt.date(2026, 9, 3))
        finding = {"key": "APS-11", "rule": "vague-title"}
        self.assertTrue(decisions.is_hidden(
            decisions.load(self.cfg), finding, today=dt.date(2026, 9, 10)))
        self.assertFalse(decisions.is_hidden(
            decisions.load(self.cfg), finding, today=dt.date(2026, 9, 18)))

    def test_accept_and_assign_hide(self):
        decisions.record(self.cfg, "accept", "APS-40", "standalone spike")
        decisions.record(self.cfg, "assign", "APS-20", "Dana will refine",
                         to="dana")
        store = decisions.load(self.cfg)
        self.assertTrue(decisions.is_hidden(
            store, {"key": "APS-40", "rule": "missing-epic"}))
        self.assertTrue(decisions.is_hidden(
            store, {"key": "APS-20", "rule": "no-estimate"}))
        self.assertEqual(decisions.assigned_to(store, "APS-20"), "dana")

    def test_star_rule_covers_every_rule_on_the_key(self):
        decisions.record(self.cfg, "snooze", "APS-11", "later",
                         until="2026-12-01", rule="*")
        store = decisions.load(self.cfg)
        self.assertTrue(decisions.is_hidden(
            store, {"key": "APS-11", "rule": "vague-title"}))
        self.assertTrue(decisions.is_hidden(
            store, {"key": "APS-11", "rule": "stale"}))

    def test_summarise_counts_verbs(self):
        decisions.record(self.cfg, "snooze", "APS-11", "x", until="2026-12-01")
        decisions.record(self.cfg, "accept", "APS-40", "y")
        decisions.record(self.cfg, "assign", "APS-20", "z", to="dana")
        hidden = [
            {"key": "APS-11", "rule": "vague-title"},
            {"key": "APS-40", "rule": "missing-epic"},
            {"key": "APS-20", "rule": "no-estimate"},
        ]
        counts = decisions.summarise(decisions.load(self.cfg), hidden)
        self.assertEqual(counts, {"hidden": 3, "snoozed": 1,
                                  "accepted": 1, "assigned": 1})
