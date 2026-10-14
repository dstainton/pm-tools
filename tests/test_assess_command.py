"""Phase 1C command and report contract tests."""

import argparse
import datetime as dt
import os
import tempfile
import unittest
from unittest.mock import patch

from commands import assess


def sample(status="complete"):
    item = {
        "project": "APS", "jql": 'project = "APS" AND statusCategory != Done',
        "retrieved_at": "2026-10-14T15:00:00+00:00", "pages": 2,
        "missing_config": ["acceptance_criteria_field"], "status": status,
        "reason": "paging interrupted" if status != "complete" else "",
        "issues": [],
    }
    facts = {
        "project": "APS", "today": "2026-10-14", "inventory_status": status,
        "inventory_reason": item["reason"], "complete": status == "complete",
        "count": 2, "ownership_evaluated": False,
        "by_type": {"Story": 2}, "by_status_category": {"new": 2},
        "created_age_bands": {"0-30": 2}, "updated_age_bands": {"0-30": 2},
        "finding_counts": {"missing-component": 2},
        "findings": [{"key": "APS-1", "url": "https://jira.example/browse/APS-1",
                      "rule": "missing-component", "detail": "No component assigned"}],
    }
    return item, facts


class RenderingTests(unittest.TestCase):
    def setUp(self):
        self.scope_patch = patch("commands.assess.dispositions.resolve",
                                 return_value={"jql": {
                                     "active": "project = APS AND status IN (1)",
                                     "completed": "project = APS AND status IN (2)",
                                     "excluded": "project = APS AND status IN (3)"},
                                     "status_names": {
                                         "active": ["To Do"], "completed": ["Done"],
                                         "excluded": ["Cancelled"]}})
        self.scope_patch.start()
        self.addCleanup(self.scope_patch.stop)
        self.count_patch = patch("commands.assess.sources.approximate_count",
                                 return_value=20)
        self.count_patch.start()
        self.addCleanup(self.count_patch.stop)

    def test_completed_summary_is_separate_approximate_count(self):
        inv, facts = sample()
        inv["completed_summary"] = {"status": "approximate", "count": 20,
                                    "jql": 'project = "APS" AND statusCategory = Done'}
        self.assertIn("Approximately 20 completed issues",
                      assess.summary([(inv, facts)]))
        report = assess.markdown([(inv, facts)])
        self.assertIn("Completed work (separate population)", report)
        self.assertIn("approximate Jira count", report)

    def test_completed_count_failure_does_not_invent_zero(self):
        cfg = {"jira": {"project": "APS"}}
        with patch("commands.assess.sources.approximate_count",
                   side_effect=ValueError("no access")):
            outcome = assess._completed(cfg, "APS")
        self.assertEqual(outcome["status"], "unavailable")
        self.assertIsNone(outcome["count"])

    def test_terminal_shows_every_review_group_and_zero_findings(self):
        inv, facts = sample()
        inv["issues"] = [
            {"key": "APS-1", "summary": "needs review", "status_category": "new"},
            {"key": "APS-2", "summary": "clean", "status_category": "new"}]
        facts["count"] = 2
        facts["findings"] = [
            {"key": "APS-1", "rule": "missing-component",
             "updated_age_days": 8, "detail": "missing", "url": ""}]
        text = assess.summary([(inv, facts)])
        self.assertIn("Investigation queue (all groups)", text)
        self.assertIn("Other backlog quality review (1 issues)", text)
        self.assertIn("No review signals (1 issues)", text)
        self.assertIn("1 issues with no review signals", assess.markdown([(inv, facts)]))

    def test_summary_and_markdown_use_same_counts(self):
        records = [sample()]
        brief = assess.summary(records)
        report = assess.markdown(records)
        self.assertIn("2 open issues", brief)
        self.assertIn("Open issues retrieved: **2**", report)
        self.assertIn("missing-component: 2", brief)
        self.assertIn("| missing-component | 2 |", report)
        self.assertIn("[APS-1](https://jira.example/browse/APS-1)", report)
        self.assertIn("not evaluated", brief)
        self.assertIn("not evaluated", report)

    def test_partial_coverage_is_visible_in_both_outputs(self):
        records = [sample("partial")]
        self.assertIn("WARNING: incomplete inventory", assess.summary(records))
        self.assertIn("Coverage limitation: **paging interrupted**",
                      assess.markdown(records))

    def test_empty_findings_have_an_explicit_explanation(self):
        inv, facts = sample()
        facts["finding_counts"] = {}
        facts["findings"] = []
        self.assertIn("None observed", assess.markdown([(inv, facts)]))

    def test_project_discovery_prefers_explicit_project(self):
        self.assertEqual(assess._projects({}, "APS, LOC"), ["APS", "LOC"])

    def test_project_discovery_uses_jira_project_without_workstreams(self):
        self.assertEqual(assess._projects({"jira": {"project": "APS"},
                                          "_workstreams": []}), ["APS"])

    def test_project_discovery_uses_selected_workstreams(self):
        cfg = {"jira": {"project": "APS"},
               "_workstreams": [{"abbrev": "X", "project": "LOC"},
                                {"abbrev": "Y", "project": "LOC"}]}
        self.assertEqual(assess._projects(cfg), ["LOC"])

    def test_run_writes_markdown_to_selected_output_folder(self):
        cfg = {"jira": {"project": "APS"}, "_workstreams": []}
        args = argparse.Namespace(project=None, out=None)
        with tempfile.TemporaryDirectory() as folder:
            args.out = folder
            inv, _ = sample()
            with patch("commands.assess.inventory.open_issues",
                       return_value=inv), patch(
                       "commands.assess.assessment.analyze",
                       return_value=sample()[1]), patch(
                       "builtins.print") as output:
                assess.run(cfg, args)
            path = os.path.join(folder, "assessment-{}.md".format(
                dt.date.today().isoformat()))
            self.assertTrue(os.path.isfile(path))
            with open(path, encoding="utf-8") as handle:
                self.assertIn("## APS", handle.read())
            self.assertTrue(output.called)

    def test_progress_starts_before_network_and_identifies_stages(self):
        cfg = {"jira": {"project": "APS"}, "_workstreams": []}
        inv, facts = sample()
        events = []
        def fetch(*args):
            events.append("fetch")
            return inv
        def started(label):
            events.append(label)
        with tempfile.TemporaryDirectory() as folder, patch(
                "commands.assess.inventory.open_issues", side_effect=fetch), patch(
                "commands.assess.assessment.analyze", return_value=facts), patch(
                "commands.assess.progress.start", side_effect=started), patch(
                "commands.assess.progress.finish") as finish, patch(
                "builtins.print"):
            assess.run(cfg, argparse.Namespace(project=None, out=folder))
        self.assertTrue(events[0].startswith("Resolving Jira dispositions"))
        self.assertTrue(events[1].startswith("Reading active Jira issues"))
        self.assertEqual(events[2], "fetch")
        self.assertTrue(any("Checking workstream ownership" in x for x in events))
        self.assertTrue(any("Analyzing backlog" in x for x in events))
        self.assertTrue(any("Writing Markdown" in x for x in events))
        self.assertGreaterEqual(finish.call_count, 2)

    def test_failed_inventory_stops_instead_of_reporting_zero(self):
        cfg = {"jira": {"project": "APS"}, "_workstreams": []}
        inv, _ = sample("failed")
        with patch("commands.assess.inventory.open_issues", return_value=inv):
            with self.assertRaises(SystemExit) as error:
                assess.run(cfg, argparse.Namespace(project=None, out=None))
        self.assertIn("paging interrupted", str(error.exception))

    def test_partial_run_reports_and_exits_nonzero(self):
        cfg = {"jira": {"project": "APS"}, "_workstreams": []}
        with tempfile.TemporaryDirectory() as folder:
            inv, facts = sample("partial")
            with patch("commands.assess.inventory.open_issues",
                       return_value=inv), patch(
                       "commands.assess.assessment.analyze",
                       return_value=facts), patch(
                       "builtins.print"):
                with self.assertRaises(SystemExit) as error:
                    assess.run(cfg, argparse.Namespace(
                        project=None, out=folder))
            self.assertEqual(error.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
