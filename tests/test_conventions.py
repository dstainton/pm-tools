"""Conventions rename the team's issue types, links and labels."""

import unittest

from core import conventions, prompts, workstreams
from commands import brief, lint, triage


class ConventionTests(unittest.TestCase):
    def test_bug_types_and_epic_types(self):
        cfg = {"conventions": {"bug_types": ["Defect"]},
               "membership": {"epic_types": ["Initiative"]}}
        self.assertTrue(triage._is_new_bug(
            {"issuetype": "Defect", "created": "2026-09-25T00:00:00.000+0000"},
            5, cfg))
        self.assertFalse(triage._is_new_bug(
            {"issuetype": "Bug", "created": "2026-09-25T00:00:00.000+0000"},
            5, cfg))
        self.assertTrue(workstreams.is_epic(cfg, {"issuetype": "Initiative"}))

    def test_blocked_by_link_names(self):
        cfg = {"conventions": {"blocked_by_links": ["depends upon"]}}
        self.assertTrue(triage._is_blocked_by({"relation": "Depends Upon"}, cfg))
        self.assertFalse(triage._is_blocked_by({"relation": "is blocked by"}, cfg))

    def test_estimate_types_include_tasks(self):
        issue = {"key": "APS-1", "url": "http://example/APS-1",
                 "issuetype": "Task", "summary": "A clear title here",
                 "status_category": "indeterminate", "story_points": None,
                 "acceptance_criteria": "Given x When y Then z",
                 "epic": "APS-1", "duedate": None, "due_date": None,
                 "start_date": None, "labels": [],
                 "updated": "2026-09-01T00:00:00.000+0000",
                 "status_changed": None}
        findings = lint.check_issue(issue, {
            "story_types": ["story"], "estimate_types": ["story", "task"],
            "require_estimate": True, "require_acceptance_criteria": False,
            "min_title_words": 3, "vague_title_alone": [], "required_fields": [],
            "stale_days": 14,
        })
        self.assertTrue(any(f["rule"] == "no-estimate" for f in findings))

    def test_note_types_follow_conventions(self):
        from core import config
        cfg = {"conventions": {"note_issuetypes": ["Story", "Defect"]}}
        prompts.validate_config(cfg)
        config._apply_convention_prompts(cfg)
        text = prompts.get(cfg, "inbox.file_note")
        self.assertIn("Story or Defect", text)

    def test_risk_label_changes_the_brief_query(self):
        from core import queries
        cfg = {"conventions": {"risk_label": "risks"}}
        queries.validate_config(cfg)
        cql = brief._risk_cql(
            {"confluence_space": "SDX", "confluence_labels": ["risks"]}, cfg)
        self.assertIn('label = "risks"', cql)


if __name__ == "__main__":
    unittest.main()
