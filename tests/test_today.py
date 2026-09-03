import datetime as dt
import os
import tempfile
import unittest

from commands import today


ISSUE = {
    "key": "APS-30",
    "url": "https://example.atlassian.net/browse/APS-30",
    "summary": "Rotate exchange signing certificates",
    "status": "To Do",
    "status_category": "new",
    "issuetype": "Story",
    "assignee": "Unassigned",
    "labels": [],
    "due_date": "2026-08-20",
    "updated": "2026-09-01T09:12:00.000+0000",
}


class ClassifyTests(unittest.TestCase):
    def test_overdue_beats_unassigned(self):
        self.assertEqual(
            today.classify_need(ISSUE, untouched_days=3,
                                today=dt.date(2026, 9, 3)),
            "overdue")

    def test_blocked_status(self):
        issue = dict(ISSUE, due_date=None, status="Blocked",
                     status_category="indeterminate", assignee="A. Lee")
        self.assertEqual(today.classify_need(issue, 3), "blocked")

    def test_blocked_label(self):
        issue = dict(ISSUE, due_date=None, labels=["blocked"],
                     assignee="A. Lee")
        self.assertEqual(today.classify_need(issue, 3), "blocked")

    def test_unassigned_open_item(self):
        issue = dict(ISSUE, due_date=None)
        self.assertEqual(today.classify_need(issue, 3), "unassigned")

    def test_untouched_assigned_item(self):
        issue = dict(ISSUE, due_date=None, assignee="B. Ray",
                     updated="2026-08-01T09:12:00.000+0000")
        self.assertEqual(today.classify_need(issue, 3), "untouched")

    def test_epics_are_not_daily_actions(self):
        issue = dict(ISSUE, issuetype="Epic", due_date=None)
        self.assertIsNone(today.classify_need(issue, 3))

    def test_done_items_are_ignored(self):
        issue = dict(ISSUE, status_category="done")
        self.assertIsNone(today.classify_need(issue, 3))

    def test_fresh_assigned_item_is_not_a_need(self):
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+0000")
        issue = dict(ISSUE, due_date=None, assignee="A. Lee", updated=now)
        self.assertIsNone(today.classify_need(issue, 3))


class ActionTests(unittest.TestCase):
    def test_needs_are_numbered_and_capped(self):
        items = []
        for n in range(8):
            items.append(dict(ISSUE, key=f"APS-{n}", due_date=None))
        opts = {"max_needs_you": 5, "untouched_days": 3}
        actions, total = today.build_needs(items, opts)
        self.assertEqual(total, 8)
        self.assertEqual([a["n"] for a in actions], [1, 2, 3, 4, 5])
        self.assertEqual(actions[0]["kind"], "unassigned")
        self.assertEqual(actions[0]["preview"]["method"], "PUT")

    def test_overdue_preview_suggests_a_due_date(self):
        preview = today.preview_payload(
            "overdue", ISSUE, today=dt.date(2026, 9, 3))
        self.assertEqual(preview["body"]["fields"]["duedate"], "2026-09-17")

    def test_state_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "today.json")
            today.save_actions(path, {"date": "2026-09-03",
                                      "actions": [{"n": 1, "key": "APS-30"}]})
            stored = today.load_actions(path)
            self.assertEqual(stored["actions"][0]["key"], "APS-30")


class RenderTests(unittest.TestCase):
    def test_screen_contains_the_four_sections(self):
        bundle = {
            "open_items": [ISSUE],
            "moved": [],
            "ready_gaps": [({"name": "Integration Platform", "abbrev": "IP"},
                            {"ready": 0, "total": 1,
                             "streams": [{"abbrev": "SDX", "name": "SDX",
                                          "not_ready": 1, "total": 1}]})],
            "sprints": [{"project": "APS", "name": "Sprint 42",
                         "goal": "Ship certificate rotation"}],
            "stale_days": 14,
            "days": 1,
            "opts": {"max_moved": 8, "max_aging": 3, "max_needs_you": 5,
                     "untouched_days": 3},
            "products": 1,
            "streams": 1,
            "needs_total": 1,
        }
        actions, _total = today.build_needs(
            [ISSUE], bundle["opts"], today=dt.date(2026, 9, 3))
        text = today.render_screen(bundle, actions, ([], 0),
                                   today=dt.date(2026, 9, 3))
        self.assertIn("SPRINT GOAL", text)
        self.assertIn("Ship certificate rotation", text)
        self.assertIn("NEEDS YOU", text)
        self.assertIn("APS-30", text)
        self.assertIn("pm do 1", text)
        self.assertIn("MOVED SINCE YESTERDAY", text)
        self.assertIn("AGING", text)
        self.assertIn("REFINEMENT GAPS", text)
        self.assertIn("pm ready -w SDX", text)


if __name__ == "__main__":
    unittest.main()
