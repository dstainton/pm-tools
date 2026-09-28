"""`pm me`: a snapshot, a window summary, and the colleague gate."""

import datetime as dt
import os
import tempfile
import unittest
from argparse import Namespace
from unittest.mock import patch

from commands import me


class _Today(dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 28)


def _cfg(role="developer"):
    return {
        "role": role,
        "jira": {"project": "APS", "base_url": "https://example.atlassian.net"},
        "workstreams": [{
            "name": "Secure Data Exchange",
            "abbrev": "SDX",
            "components": ["Secure Data Exchange"],
        }],
    }


def _open_issues():
    return [
        {
            "key": "APS-2",
            "summary": "In the stream",
            "status": "In Progress",
            "status_category": "indeterminate",
            "issuetype": "Story",
            "components": ["Secure Data Exchange"],
            "updated": "2026-09-27T00:00:00.000+0000",
            "labels": [],
        },
        {
            "key": "APS-3",
            "summary": "No component",
            "status": "To Do",
            "status_category": "new",
            "issuetype": "Story",
            "components": [],
            "updated": "2026-09-01T00:00:00.000+0000",
            "labels": [],
        },
    ]


def _finished():
    return [{
        "key": "APS-9",
        "summary": "Shipped",
        "status": "Done",
        "status_category": "done",
        "issuetype": "Story",
        "components": ["Secure Data Exchange"],
        "updated": "2026-09-20T00:00:00.000+0000",
        "comments": ["2026-09-20 Dana: shipped"],
    }]


class MeTests(unittest.TestCase):
    def _args(self, folder, **overrides):
        values = dict(who=None, since=None, days=None, sprint=None, summary=False,
                      audience=None, out=folder)
        values.update(overrides)
        return Namespace(**values)

    def test_snapshot_lists_open_work_and_skips_memory_and_the_model(self):
        calls = []

        def detailed(_jira, jql):
            calls.append(jql)
            return _open_issues()

        with tempfile.TemporaryDirectory() as folder, \
                patch("commands.me.dt.date", _Today), \
                patch("commands.me.sources.fetch_jira_detailed", side_effect=detailed), \
                patch("commands.me.sources.fetch_jira_keys", return_value=["APS-2"]), \
                patch("commands.me.sources.fetch_active_sprints", return_value=[{
                    "name": "Sprint 139", "goal": "Ship the export", "id": 139}]), \
                patch("core.state.save_state") as save, \
                patch("core.model.call_model") as model:
            me.run(_cfg(), self._args(folder))
            model.assert_not_called()
            save.assert_not_called()
            self.assertTrue(any("currentUser()" in jql for jql in calls))
            self.assertTrue(any("statusCategory != Done" in jql for jql in calls))
            path = os.path.join(folder, "me_snapshot_2026-09-28.md")
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        self.assertIn("Outside your workstreams", text)
        self.assertIn("APS-3", text)
        self.assertIn("APS-2", text)
        self.assertIn("Sprint 139", text)
        self.assertIn("Ship the export", text)
        self.assertIn("Snapshot.", text)

    def test_a_sprint_summary_and_a_day_window_leave_memory_alone(self):
        def detailed(_jira, jql):
            if "statusCategory = Done" in jql:
                return _finished()
            return _open_issues()

        def sprints(_jira, _project, states=None):
            return [{
                "id": 139, "name": "Sprint 139", "state": "active",
                "start": "2026-09-15", "end": "2026-09-28",
            }]

        with tempfile.TemporaryDirectory() as folder, \
                patch("commands.me.dt.date", _Today), \
                patch("commands.me.sources.fetch_jira_detailed", side_effect=detailed), \
                patch("core.sources.fetch_sprints", side_effect=sprints), \
                patch("commands.me.comments.attach") as attach, \
                patch("core.state.save_state") as save:
            me.run(_cfg(), self._args(folder, sprint="open"))
            attach.assert_called()
            self.assertTrue(attach.call_args.kwargs.get("author"))
            save.assert_not_called()
            path = os.path.join(folder, "me_summary_139_2026-09-28.md")
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        self.assertIn("Finished", text)
        self.assertIn("APS-9", text)
        self.assertIn("Still open", text)
        self.assertIn("APS-2", text)
        self.assertIn("Dana", text)

        with tempfile.TemporaryDirectory() as folder, \
                patch("commands.me.dt.date", _Today), \
                patch("commands.me.sources.fetch_jira_detailed", side_effect=detailed) as fetch, \
                patch("commands.me.comments.attach"), \
                patch("core.state.save_state") as save:
            me.run(_cfg(), self._args(folder, days=14))
            save.assert_not_called()
            joined = " ".join(call.args[1] for call in fetch.call_args_list)
            self.assertIn('resolved >= "2026-09-14"', joined)
            with open(os.path.join(folder, "me_summary_2026-09-14_2026-09-28.md"),
                      encoding="utf-8") as fh:
                text = fh.read()
        self.assertIn("Finished", text)
        self.assertIn("Still open", text)

    def test_who_resolves_for_pm_and_is_refused_for_work(self):
        def detailed(_jira, jql):
            self.assertIn('assignee = "abc"', jql)
            return _open_issues()

        with tempfile.TemporaryDirectory() as folder, \
                patch("commands.me.dt.date", _Today), \
                patch("commands.me.sources.fetch_jira_detailed", side_effect=detailed), \
                patch("commands.me.sources.fetch_jira_keys", return_value=[]), \
                patch("commands.me.sources.fetch_active_sprints", return_value=[]), \
                patch("commands.me.sources.resolve_assignee",
                      return_value={"accountId": "abc", "displayName": "A. Lee"}):
            me.run(_cfg("pm"), self._args(folder, who="A. Lee"))
            with open(os.path.join(folder, "me_snapshot_2026-09-28.md"),
                      encoding="utf-8") as fh:
                self.assertIn("# A. Lee's work", fh.read())

        with self.assertRaises(SystemExit) as caught:
            me.run(_cfg("developer"), self._args(folder, who="A. Lee"))
        self.assertIn("product manager", str(caught.exception))

        calls = []

        def own(_jira, jql):
            calls.append(jql)
            return []

        with tempfile.TemporaryDirectory() as folder, \
                patch("commands.me.dt.date", _Today), \
                patch("commands.me.sources.fetch_jira_detailed", side_effect=own), \
                patch("commands.me.sources.fetch_jira_keys", return_value=[]), \
                patch("commands.me.sources.fetch_active_sprints", return_value=[]):
            me.run(_cfg("developer"), self._args(folder))
        self.assertTrue(any("currentUser()" in jql for jql in calls))


if __name__ == "__main__":
    unittest.main()
