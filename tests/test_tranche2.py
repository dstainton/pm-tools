"""Tranche 2: coverage, sprint risk, goals, ready size, inbox edit, notes."""

import datetime as dt
import json
import os
import sys
import tempfile
import textwrap
import unittest
from argparse import Namespace
from unittest.mock import patch

from commands import coverage, inbox, products, ready, release_notes, report, today
from core import checklist, migrations


LIVE = textwrap.dedent("""\
    # keep this comment
    config_version: 1
    jira:
      api_token: "secret-token"
    workstreams:
      - name: "Secure Data Exchange"
        abbrev: "SDX"
        components: ["Secure Data Exchange"]
    """)


class MigrationTests(unittest.TestCase):
    def test_version_2_inserts_max_points_and_nothing_else(self):
        updated = migrations.to_version_2(LIVE)
        self.assertEqual(migrations.read_version(updated), 2)
        self.assertIn("max_points: 8", updated)
        self.assertIn("secret-token", updated)
        self.assertIn("# keep this comment", updated)
        self.assertNotIn("product_goal", updated)
        self.assertNotIn("definition_of_done", updated)
        again = migrations.apply_migrations(updated, migrations.MIGRATIONS, 2)
        self.assertEqual(again, updated)

    def test_version_2_keeps_a_threshold_already_set(self):
        text = "config_version: 1\nready:\n  max_points: 13\n  blocking_criteria:\n    - clear-title\n"
        updated = migrations.to_version_2(text)
        self.assertEqual(updated.count("max_points"), 1)
        self.assertIn("max_points: 13", updated)
        self.assertEqual(migrations.read_version(updated), 2)

    def test_version_2_inserts_inside_an_existing_ready_block(self):
        text = ("config_version: 1\nready:\n  blocking_criteria:\n"
                "    - clear-title\n")
        updated = migrations.to_version_2(text)
        self.assertIn("ready:\n  max_points: 8\n  blocking_criteria:", updated)


class CoverageTests(unittest.TestCase):
    def test_classify_splits_the_three_lists(self):
        issues = [
            {"key": "APS-3", "summary": "Housekeeping"},
            {"key": "APS-50", "summary": "Metrics"},
            {"key": "APS-10", "summary": "Status"},
        ]
        result = coverage.classify(
            issues,
            {"APS-50": ["SDX", "APS"], "APS-10": ["SDX"]},
            ["Secure Data Exchange", "Documentation"],
            ["Secure Data Exchange"],
        )
        self.assertEqual([i["key"] for i in result["unclaimed"]], ["APS-3"])
        self.assertEqual(result["overlap"][0]["workstreams"], ["SDX", "APS"])
        self.assertEqual(result["unused"], ["Documentation"])


class SprintRiskTests(unittest.TestCase):
    def test_future_sprint_counts_not_started_and_blocked(self):
        sprint = {"end": "2026-09-10", "goal": "Ship it"}
        issues = [
            {"key": "A", "issuetype": "Story", "status_category": "new",
             "status": "To Do", "labels": []},
            {"key": "B", "issuetype": "Story", "status_category": "indeterminate",
             "status": "Blocked", "labels": []},
            {"key": "C", "issuetype": "Epic", "status_category": "new",
             "status": "To Do", "labels": []},
            {"key": "D", "issuetype": "Story", "status_category": "done",
             "status": "Done", "labels": ["blocked"]},
        ]
        sentence = today.sprint_risk_sentence(
            sprint, issues, today=dt.date(2026, 9, 3))
        self.assertEqual(
            sentence, "Sprint ends in 7 days. Not started: 1. Blocked: 1.")

    def test_a_sprint_that_has_ended_does_not_use_a_negative_count(self):
        sentence = today.sprint_risk_sentence(
            {"end": "2026-09-10"}, [], today=dt.date(2026, 9, 23))
        self.assertEqual(
            sentence, "Sprint ended 13 days ago. Not started: 0. Blocked: 0.")

    def test_no_end_date_omits_the_line(self):
        self.assertIsNone(today.sprint_risk_sentence({"goal": "Ship it"}, []))


class ReadySizeTests(unittest.TestCase):
    def _issue(self, points):
        return {
            "key": "APS-1",
            "url": "https://example/browse/APS-1",
            "summary": "Rotate the exchange certificates",
            "status": "To Do",
            "status_category": "new",
            "issuetype": "Story",
            "components": ["Secure Data Exchange"],
            "story_points": points,
            "description": "Acceptance criteria: the job finishes.",
            "acceptance_criteria": "Acceptance criteria: the job finishes.",
            "due_date": None,
            "start_date": None,
            "updated": None,
            "epic": "APS-9",
        }

    def test_over_the_threshold_fails_only_when_the_rule_is_listed(self):
        lint_cfg = {"story_types": ["story"], "require_estimate": True,
                    "min_title_words": 3, "vague_title_terms": [],
                    "require_acceptance_criteria": False}
        big = self._issue(13)
        off = ready.evaluate_issue(
            big, lint_cfg, blocking=set(), deep_findings=None, max_points=8)
        self.assertTrue(off["ready"])
        on = ready.evaluate_issue(
            big, lint_cfg, blocking={"too-big-for-a-sprint"},
            deep_findings=None, max_points=8)
        self.assertFalse(on["ready"])
        self.assertEqual(on["failed"][0]["criterion"], "too-big-for-a-sprint")

    def test_a_missing_estimate_does_not_also_fail_the_size_rule(self):
        self.assertIsNone(ready.size_failure(self._issue(None), 8))
        self.assertIsNone(ready.size_failure(self._issue(0), 8))
        self.assertIsNone(ready.size_failure(self._issue(8), 8))


class ChecklistTests(unittest.TestCase):
    def test_product_list_wins_and_strings_stay_reminders(self):
        cfg = {"definition_of_done": ["Shared reminder"]}
        product = {"definition_of_done": [
            "Shown",
            {"text": "Deployed", "label": "deployed"},
        ]}
        items = checklist.definition_items(cfg, product)
        self.assertEqual(items[0], {"text": "Shown", "label": None})
        self.assertEqual(items[1]["label"], "deployed")
        self.assertEqual(checklist.product_goal({}), "")
        self.assertEqual(
            checklist.product_goal({"product_goal": "  Ship it  "}), "Ship it")

    def test_report_prints_the_goal_and_the_increment(self):
        cfg = {
            "products": [{
                "name": "Integration Platform",
                "abbrev": "IP",
                "product_goal": "Tenants exchange data in a day",
                "definition_of_done": [
                    "Tests pass",
                    {"text": "On staging", "label": "staged"},
                ],
            }],
            "workstreams": [{"name": "Secure Data Exchange", "abbrev": "SDX",
                             "product": "IP"}],
            "output": {"audience": "directors"},
        }
        ws = cfg["workstreams"][0]
        text = report.build_report(cfg, [(ws, "Body.")], [], "")
        self.assertIn("Product Goal: Tenants exchange data in a day", text)
        self.assertIn("### Increment", text)
        self.assertIn("Tests pass", text)
        self.assertIn("label: staged", text)

    def test_label_gap_ignores_reminders(self):
        gaps = ready.label_gaps(
            [{"key": "APS-9", "summary": "Done item", "labels": []}],
            [{"text": "Remember this", "label": None},
             {"text": "On staging", "label": "staged"}],
        )
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["label"], "staged")


class InboxEditTests(unittest.TestCase):
    def test_edit_sticks_and_create_prefers_it(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg = {
                "state": {"shared_path": folder},
                "jira": {"project": "APS", "base_url": "https://example"},
                "workstreams": [{
                    "name": "Secure Data Exchange",
                    "abbrev": "SDX",
                    "components": ["Secure Data Exchange"],
                }],
                "model": {},
            }
            inbox._note(cfg, Namespace(
                text=["customer wants SSO"], workstream=None, product=None))
            inbox._edit(cfg, Namespace(
                target=1, title="Export the SSO audit log", workstream="SDX",
                criteria="Given an admin, when they export, then a file is saved."))
            with open(os.path.join(folder, "inbox.json"), encoding="utf-8") as fh:
                note = json.load(fh)["notes"][0]
            self.assertEqual(note["title"], "Export the SSO audit log")
            self.assertNotIn("jira", json.dumps(note).lower())

            captured = {}

            def _apply(_cfg, _args, action):
                captured["action"] = action
                return {"key": "APS-99"}

            with patch.object(inbox, "_suggest", return_value={
                    "title": "Model title", "workstream": "NOPE",
                    "criteria": "model criteria", "issuetype": "Bug"}):
                with patch("core.writes.apply_action", side_effect=_apply):
                    inbox._create(cfg, Namespace(
                        target=1, title=None, workstream=None, issuetype=None,
                        criteria=None, yes=True, dry_run=False))
            fields = captured["action"]["body"]["fields"]
            self.assertEqual(fields["summary"], "Export the SSO audit log")
            self.assertEqual(fields["issuetype"]["name"], "Bug")
            self.assertIn("a file is saved", json.dumps(fields["description"]))
            self.assertEqual(fields["components"], [{"name": "Secure Data Exchange"}])


class ReleaseNoteTests(unittest.TestCase):
    def test_model_skip_still_prints_the_issues(self):
        rows = [{
            "product_name": "Integration Platform",
            "product_abbrev": "IP",
            "workstream_name": "Secure Data Exchange",
            "workstream_abbrev": "SDX",
            "key": "APS-10",
            "summary": "Publish the status endpoint",
            "url": "https://example/browse/APS-10",
        }]
        text = release_notes.render("2026-08-01", None, rows, None)
        self.assertIn("The model was skipped.", text)
        self.assertIn("APS-10: Publish the status endpoint", text)
        self.assertIn("## Integration Platform (IP)", text)

    def test_since_must_be_a_date(self):
        with self.assertRaises(SystemExit):
            release_notes._since("August")


class ProductGoalWriteTests(unittest.TestCase):
    def test_add_writes_the_goal_and_skips_it_when_empty(self):
        text = "config_version: 2\nproducts: []\nworkstreams: []\n"
        updated = products.add_entry_to_text(text, {
            "name": "Billing",
            "abbrev": "BILL",
            "project": None,
            "product_goal": "Invoices go out the same day",
        })
        self.assertIn('product_goal: "Invoices go out the same day"', updated)
        plain = products.add_entry_to_text(text, {
            "name": "Billing",
            "abbrev": "BILL",
            "project": None,
        })
        self.assertNotIn("product_goal", plain)


class HelpTests(unittest.TestCase):
    def test_help_names_the_new_flags(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pm = os.path.join(root, "pm.py")

        def help_for(*args):
            proc = __import__("subprocess").run(
                [sys.executable, pm, *args],
                capture_output=True, text=True, encoding="utf-8", timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return proc.stdout

        self.assertIn("--goal", help_for("products", "--help"))
        self.assertIn("--sprint", help_for("metrics", "--help"))
        self.assertIn("edit", help_for("inbox", "--help"))
        self.assertIn("--criteria", help_for("inbox", "--help"))
        self.assertIn("--since", help_for("release-notes", "--help"))
        self.assertIn("working agreement", help_for("ready", "--help"))


if __name__ == "__main__":
    unittest.main()
