"""The report window changes what is fetched."""

import datetime as dt
import unittest
from unittest.mock import patch

from commands import report
from core import window as window_core


class WindowFetchTests(unittest.TestCase):
    def test_explicit_since_is_the_page_cutoff(self):
        seen = {}

        def fake_fetch(cfg, cql, prefix, start, since=None):
            seen["since"] = since
            return [], start

        window = {"explicit": True, "start": dt.date(2026, 6, 1), "sprint_id": None}
        with patch("core.sources.fetch_jira", return_value=([], 1)), \
             patch("core.sources.fetch_confluence", side_effect=fake_fetch), \
             patch("core.sources.fetch_sharepoint", return_value=([], 1)), \
             patch("core.workstreams.scope_jql", return_value="project = APS"):
            report.prepare(
                {"pages": {}, "comments": {}, "confluence": {}, "sharepoint": {},
                 "jira": {}},
                {"abbrev": "SDX", "name": "SDX"},
                {"SDX": {"_ran_at": "2026-01-01T00:00:00+00:00"}},
                window)
        self.assertEqual(seen["since"], dt.date(2026, 6, 1))

    def test_second_run_uses_the_workstream_ran_at(self):
        seen = {}

        def fake_cutoff(snapshot, opts, now=None):
            seen["ran"] = snapshot.get("_ran_at")
            return dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)

        with patch("core.sources.fetch_jira", return_value=([], 1)), \
             patch("core.sources.fetch_confluence", return_value=([], 1)), \
             patch("core.sources.fetch_sharepoint", return_value=([], 1)), \
             patch("core.workstreams.scope_jql", return_value="project = APS"), \
             patch("core.comments.report_cutoff", side_effect=fake_cutoff), \
             patch("core.comments.attach"):
            report.prepare(
                {"pages": {}, "comments": {}, "confluence": {}, "sharepoint": {},
                 "jira": {}},
                {"abbrev": "SDX", "name": "SDX"},
                {"SDX": {"_ran_at": "2026-09-01T00:00:00+00:00"}},
                {"explicit": False, "sprint_id": None})
        self.assertEqual(seen["ran"], "2026-09-01T00:00:00+00:00")

    def test_sprint_override_reaches_the_report_scope(self):
        seen = {}

        def fake_scope(cfg, ws, name, overrides=None, days=None):
            if name == "report":
                seen["overrides"] = overrides
            return "project = APS"

        with patch("core.sources.fetch_jira", return_value=([], 1)), \
             patch("core.sources.fetch_confluence", return_value=([], 1)), \
             patch("core.sources.fetch_sharepoint", return_value=([], 1)), \
             patch("core.workstreams.scope_jql", side_effect=fake_scope), \
             patch("core.comments.attach"):
            report.prepare(
                {"pages": {}, "comments": {}, "confluence": {}, "sharepoint": {},
                 "jira": {}},
                {"abbrev": "SDX", "name": "SDX"}, {},
                {"explicit": True, "start": dt.date(2026, 6, 1), "sprint_id": 10})
        self.assertEqual(seen["overrides"], {"sprint": 10})

    def test_resolve_returns_the_sprint_id(self):
        cfg = {"jira": {}}
        sprints = [{"id": 10, "name": "Sprint 10", "state": "active",
                    "start": "2026-06-01", "end": "2026-06-14"}]

        class Args:
            since = None
            days = None
            weeks = None
            sprint = "10"

        with patch("core.sources.fetch_sprints", return_value=sprints):
            window = window_core.resolve(cfg, Args(), projects=["APS"])
        self.assertEqual(window["sprint_id"], 10)


if __name__ == "__main__":
    unittest.main()
