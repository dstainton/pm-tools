"""Epic parent walks, child counts, and the signal rule."""

import datetime as dt
import unittest
from unittest.mock import patch

from core import epics, sources
from tests.test_cli_end_to_end import backlog


def _raw(issue):
    category = {"To Do": "new", "In Progress": "indeterminate", "Done": "done"}.get(
        issue.get("status_category"), "new")
    return {
        "key": issue["key"],
        "fields": {
            "summary": issue.get("summary"),
            "issuetype": {"name": issue.get("issuetype")},
            "status": {"name": issue.get("status_name"),
                       "statusCategory": {"key": category}},
            "parent": {"key": issue["parent"]} if issue.get("parent") else None,
            "duedate": issue.get("duedate"),
            "updated": issue.get("updated"),
            "labels": issue.get("labels") or [],
        },
    }


def _item(issue):
    raw = _raw(issue)
    f = raw["fields"]
    return {
        "source": "Jira", "key": issue["key"], "uid": issue["key"],
        "parent": (f["parent"] or {}).get("key"),
        "issuetype": issue.get("issuetype"),
        "summary": issue.get("summary"),
        "status": issue.get("status_name"),
        "status_category": f["status"]["statusCategory"]["key"],
        "due": issue.get("duedate") or "",
        "updated": issue.get("updated"),
        "labels": issue.get("labels") or [],
    }


class EpicTests(unittest.TestCase):
    def setUp(self):
        self.by_key = {issue["key"]: issue for issue in backlog()}

    def _fetch(self, cfg, keys, fields):
        return [_raw(self.by_key[key]) for key in keys if key in self.by_key]

    def test_a_subtask_resolves_to_its_epic(self):
        item = _item(self.by_key["APS-12"])
        with patch("core.sources.fetch_issues_by_key", side_effect=self._fetch):
            parents, fields = epics.parent_map({"jira": {}}, [item], ["Epic"])
        types = {key: facts["issuetype"] for key, facts in fields.items()}
        self.assertEqual(epics.epic_of("APS-12", parents, types, ["Epic"]), "APS-1")

    def test_an_out_of_scope_epic_is_marked(self):
        item = _item(self.by_key["APS-31"])
        with patch("core.sources.fetch_issues_by_key", side_effect=self._fetch), \
             patch("core.workstreams.get_epic_keys", return_value=["APS-1"]), \
             patch("core.epics.child_counts", return_value={}):
            rows = epics.build(
                {"jira": {}, "membership": {"epic_types": ["Epic"]}},
                {"abbrev": "SDX"}, [item],
                {"start": dt.date(2026, 9, 1), "explicit": True}, ([], [], []))
        epic = next(row for row in rows if row["key"] == "APS-3")
        self.assertFalse(epic["in_scope"])

    def test_signal_order_done_beats_at_risk(self):
        today = dt.date(2026, 9, 25)
        word, _reason = epics.signal(
            {"status_category": "done", "due": "2026-09-01"},
            {"total": 2, "done": 0, "in_progress": 0, "blocked": 1},
            today, today, 14, True)
        self.assertEqual(word, "Done")
        word, reason = epics.signal(
            {"status_category": "indeterminate", "due": "2026-09-01"},
            {"total": 2, "done": 0, "in_progress": 1, "blocked": 1},
            today, today, 14, True)
        self.assertEqual(word, "At risk")
        self.assertIn("blocked", reason)
        word, _reason = epics.signal(
            {"status_category": "indeterminate", "due": ""},
            {"total": 1, "done": 0, "in_progress": 1, "blocked": 0},
            today, today, 14, False)
        self.assertEqual(word, "No movement")
        word, _reason = epics.signal(
            {"status_category": "new", "due": ""},
            {"total": 1, "done": 0, "in_progress": 0, "blocked": 0},
            today, today, 14, True)
        self.assertEqual(word, "Not started")
        word, _reason = epics.signal(
            {"status_category": "indeterminate", "due": "2026-12-01"},
            {"total": 4, "done": 3, "in_progress": 1, "blocked": 0},
            today, today, 14, True)
        self.assertEqual(word, "On track")

    def test_child_counts_skip_subtasks(self):
        raws = [
            _raw(self.by_key["APS-10"]),
            _raw(self.by_key["APS-12"]),
        ]

        def search(cfg, jql, fields=None, max_items=None):
            self.assertIn("parent IN", jql)
            self.assertNotIn("APS-12", jql)
            return raws

        with patch("core.sources.search_issues", side_effect=search):
            counts = epics.child_counts({"jira": {}}, ["APS-1"], {})
        self.assertEqual(counts["APS-1"]["total"], 1)

    def test_parent_is_requested_when_the_field_list_omits_it(self):
        names = sources._report_fields({"fields": "summary,status"})
        self.assertIn("parent", names)


if __name__ == "__main__":
    unittest.main()
