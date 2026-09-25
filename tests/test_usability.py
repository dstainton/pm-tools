"""Behaviour from the usability plan: one queue, windows, pages, setup, MCP."""

import datetime as dt
import json
import os
import tempfile
import unittest
from argparse import Namespace

from commands import mcp_server, setup
from core import filters, migrations, model, pages, window
from commands import today


class QueueTests(unittest.TestCase):
    def test_one_issue_keeps_one_number(self):
        issue = {"key": "APS-50", "summary": "Rotate", "age_days": 3,
                 "due_date": "2020-01-01", "issuetype": "Story",
                 "status": "In Progress", "status_category": "In Progress"}
        other = dict(issue, workstream="SDX")
        issue = dict(issue, workstream="APS")
        opts = {"untouched_days": 5, "max_needs_you": 8}
        actions, total = today.build_needs(
            [issue, other], opts, today=dt.date(2026, 9, 3))
        self.assertEqual(total, 1)
        self.assertEqual([a["key"] for a in actions], ["APS-50"])

    def test_due_date_uses_the_sprint_end(self):
        when = today.suggested_due(dt.date(2026, 9, 3), sprint_end="2026-09-18")
        self.assertEqual(when, dt.date(2026, 9, 18))

    def test_an_ended_sprint_is_not_the_goal(self):
        bundle = {
            "open_items": [], "products": 1, "moved": [], "ready_gaps": [],
            "opts": {"max_moved": 5},
            "sprints": [{
                "name": "APS SP137", "project": "APS",
                "goal": "1. Ship it", "end": "2026-09-01",
            }],
            "sprint_items": {},
        }
        text = today.render_screen(
            bundle, [], ([], 0), today=dt.date(2026, 9, 24))
        self.assertIn("ENDED SPRINT", text)
        self.assertNotIn("SPRINT GOAL", text)


class WindowTests(unittest.TestCase):
    def test_sprint_number_matches_the_name(self):
        sprints = [
            {"id": 10, "name": "APS SP137", "state": "closed", "end": "2026-09-01"},
            {"id": 11, "name": "APS SP138", "state": "active",
             "start": "2026-09-08", "end": "2026-09-19"},
        ]
        chosen = window.resolve_sprint(sprints, "138")
        self.assertEqual(chosen["id"], 11)

    def test_ambiguous_sprint_lists_candidates(self):
        sprints = [
            {"id": 1, "name": "APS 138", "state": "active"},
            {"id": 2, "name": "ITK 138", "state": "active"},
        ]
        with self.assertRaises(window.WindowError) as caught:
            window.resolve_sprint(sprints, "138")
        self.assertIn("Available:", str(caught.exception))

    def test_sprint_id_compiles_to_jql(self):
        self.assertEqual(filters.compile_scope({"sprint": 1234}), "sprint = 1234")


class PageTests(unittest.TestCase):
    def test_a_decision_page_is_not_cut_to_180_characters(self):
        body = (
            "The team met on 18 September to decide the certificate rotation "
            "cadence. Options considered were 30, 60 and 90 days. Security "
            "argued for 30 on the grounds of exposure window. "
            "DECISION: rotate every 90 days, automated from October."
        )
        item = {"source": "Confluence", "ref": "SDX-C1", "title": "Decision",
                "detail": body, "watch": "2026-09-20"}
        kept = pages.apply_excerpt([item], pages.settings({}), cutoff=None)
        text = model.build_material(kept, detail_limit=180)
        self.assertIn("DECISION: rotate every 90 days", text)


class SetupTests(unittest.TestCase):
    def test_noninteractive_setup_names_the_flags(self):
        with self.assertRaises(SystemExit) as caught:
            setup.run(Namespace())
        self.assertIn("--site", str(caught.exception))
        self.assertIn("--token-env", str(caught.exception))

    def test_flags_do_not_replace_a_value(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.yaml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('jira:\n  base_url: "https://kept.atlassian.net"\n'
                         '  email: ""\n  project: ""\n')
            setup.run(Namespace(
                path=path, site="dpdd", email="pm@example.com",
                token_env="JIRA_TOKEN", project="APS", token=None,
                model_endpoint=None, model_name=None, section=None, yes=True))
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        self.assertIn("https://kept.atlassian.net", text)
        self.assertIn("pm@example.com", text)
        self.assertIn("${ENV:JIRA_TOKEN}", text)
        self.assertIn("APS", text)


class McpTests(unittest.TestCase):
    def test_write_commands_are_not_tools(self):
        names = mcp_server.tool_names()
        self.assertIn("today", names)
        self.assertNotIn("do", names)
        self.assertNotIn("refine", names)
        reply = mcp_server.handle({"method": "tools/call", "params": {"name": "do"}})
        self.assertTrue(reply.get("isError"))


class MigrationTests(unittest.TestCase):
    def test_version_4_gains_a_pages_block(self):
        text = "config_version: 4\nconfluence:\n  lookback_days: 7\n"
        updated = migrations.apply_migrations(text, migrations.MIGRATIONS, 5)
        self.assertEqual(migrations.read_version(updated), 5)
        self.assertIn("pages:", updated)
        self.assertIn("excerpt_chars: 2000", updated)
        again = migrations.apply_migrations(updated, migrations.MIGRATIONS, 5)
        self.assertEqual(again, updated)

    def test_version_5_gains_audiences_and_not_prompts(self):
        text = ("config_version: 5\npages:\n  enabled: true\n"
                "confluence:\n  lookback_days: 7\nscopes:\n  report: {}\noutput:\n  file: x\n")
        updated = migrations.apply_migrations(text, migrations.MIGRATIONS, 6)
        self.assertEqual(migrations.read_version(updated), 6)
        self.assertIn("audiences:", updated)
        self.assertIn("scope: space", updated)
        self.assertIn("content_types:", updated)
        self.assertIn("refine_history:", updated)
        self.assertNotIn("prompts:", updated)
        self.assertNotIn("queries:", updated)
        again = migrations.apply_migrations(updated, migrations.MIGRATIONS, 6)
        self.assertEqual(again, updated)
