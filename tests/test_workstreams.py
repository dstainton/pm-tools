import unittest
from unittest.mock import patch

from core import workstreams
from commands import lint, ready


JIRA = {
    "base_url": "https://example.atlassian.net",
    "email": "pm@example.com",
    "api_token": "token",
    "max_results": 100,
}


def inherited_ws(**overrides):
    ws = {
        "name": "Secure Data Exchange",
        "abbrev": "SDX",
        "jira_project": "APS",
        "epic_components": ["Secure Data Exchange"],
        "jira_jql": "sprint in openSprints()",
        "roadmap_jql": "statusCategory != Done",
        "lint_jql": "statusCategory != Done",
        "standup_moved_jql": "updated >= -{days}d",
        "standup_wip_jql": 'statusCategory = "In Progress"',
        "_resolved_epic_keys": ["APS-10", "APS-20"],
    }
    ws.update(overrides)
    return ws


class WorkstreamJqlTests(unittest.TestCase):
    def test_epic_selector_uses_project_and_components(self):
        ws = inherited_ws()
        ws.pop("_resolved_epic_keys")
        self.assertEqual(
            workstreams.epic_selector_jql(ws),
            'project = "APS" AND issuetype = Epic '
            'AND component IN ("Secure Data Exchange")',
        )

    def test_report_scope_is_children_of_workstream_epics(self):
        jql = workstreams.resolve_jql(JIRA, inherited_ws(), "jira_jql")
        self.assertIn('project = "APS"', jql)
        self.assertIn('parentEpic IN (APS-10, APS-20)', jql)
        self.assertIn('sprint in openSprints()', jql)
        self.assertNotIn('key IN (APS-10, APS-20) OR', jql)

    def test_roadmap_scope_is_epics_only(self):
        jql = workstreams.resolve_jql(JIRA, inherited_ws(), "roadmap_jql")
        self.assertIn('key IN (APS-10, APS-20)', jql)
        self.assertNotIn('parentEpic IN', jql)
        self.assertIn('statusCategory != Done', jql)

    def test_lint_scope_includes_epics_and_descendants(self):
        jql = workstreams.resolve_jql(JIRA, inherited_ws(), "lint_jql")
        self.assertIn('key IN (APS-10, APS-20)', jql)
        self.assertIn('parentEpic IN (APS-10, APS-20)', jql)

    def test_ready_fallback_stays_child_only(self):
        jql = workstreams.resolve_jql(
            JIRA, inherited_ws(), "ready_jql", fallback_field="jira_jql")
        self.assertIn('parentEpic IN (APS-10, APS-20)', jql)
        self.assertNotIn('key IN (APS-10, APS-20) OR', jql)
        self.assertIn('sprint in openSprints()', jql)

    def test_standup_substitution(self):
        jql = workstreams.resolve_jql(
            JIRA,
            inherited_ws(),
            "standup_moved_jql",
            substitutions={"days": 3},
        )
        self.assertIn('updated >= -3d', jql)
        self.assertIn('parentEpic IN (APS-10, APS-20)', jql)

    def test_legacy_direct_jql_is_unchanged(self):
        ws = {"abbrev": "OLD", "jira_jql": "project = OLD AND sprint in openSprints()"}
        self.assertEqual(
            workstreams.resolve_jql(JIRA, ws, "jira_jql"),
            "project = OLD AND sprint in openSprints()",
        )

    def test_epic_discovery_is_cached_per_workstream(self):
        ws = inherited_ws()
        ws.pop("_resolved_epic_keys")
        with patch("core.workstreams.sources.fetch_jira_keys", return_value=["APS-10"]) as fetch:
            workstreams.resolve_jql(JIRA, ws, "jira_jql")
            workstreams.resolve_jql(JIRA, ws, "roadmap_jql")
            self.assertEqual(fetch.call_count, 1)

    def test_no_matching_epics_returns_no_query(self):
        ws = inherited_ws(_resolved_epic_keys=[])
        self.assertIsNone(workstreams.resolve_jql(JIRA, ws, "jira_jql"))


class LintInheritanceTests(unittest.TestCase):
    def _issue(self):
        return {
            "key": "APS-123",
            "url": "https://example.atlassian.net/browse/APS-123",
            "summary": "Implement exchange status endpoint",
            "status_category": "new",
            "status": "To Do",
            "issuetype": "Story",
            "components": [],
            "epic": "APS-10",
            "story_points": 3,
            "start_date": None,
            "due_date": None,
            "updated": None,
            "description": "Acceptance criteria: returns current status.",
            "acceptance_criteria": "Acceptance criteria: returns current status.",
        }

    def test_missing_component_is_not_flagged_when_inherited(self):
        cfg = {
            "required_fields": ["component", "epic"],
            "require_acceptance_criteria": False,
            "require_estimate": False,
            "min_title_words": 3,
            "vague_title_terms": [],
        }
        findings = lint.check_issue(self._issue(), cfg, component_inherited=True)
        self.assertNotIn("missing-component", {f["rule"] for f in findings})

    def test_missing_component_still_works_for_legacy_scope(self):
        cfg = {
            "required_fields": ["component", "epic"],
            "require_acceptance_criteria": False,
            "require_estimate": False,
            "min_title_words": 3,
            "vague_title_terms": [],
        }
        findings = lint.check_issue(self._issue(), cfg, component_inherited=False)
        self.assertIn("missing-component", {f["rule"] for f in findings})

    def test_ready_component_criterion_does_not_fail_inherited_child(self):
        cfg = {
            "required_fields": ["component", "epic"],
            "require_acceptance_criteria": False,
            "require_estimate": False,
            "min_title_words": 3,
            "vague_title_terms": [],
        }
        verdict = ready.evaluate_issue(
            self._issue(),
            cfg,
            blocking={"has-component"},
            deep_findings=None,
            component_inherited=True,
        )
        self.assertTrue(verdict["ready"])


if __name__ == "__main__":
    unittest.main()
