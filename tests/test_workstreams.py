import unittest
from unittest.mock import patch

from core import workstreams
from commands import lint, ready


def base_cfg(**overrides):
    cfg = {
        "jira": {
            "base_url": "https://example.atlassian.net",
            "email": "pm@example.com",
            "api_token": "token",
            "project": "APS",
            "max_results": 100,
        },
    }
    cfg.update(overrides)
    return cfg


def component_ws(**overrides):
    ws = {
        "name": "Secure Data Exchange",
        "abbrev": "SDX",
        "components": ["Secure Data Exchange"],
        "_resolved_epic_keys": ["APS-10", "APS-20"],
        "_resolved_tagged_keys": ["APS-30"],
    }
    ws.update(overrides)
    return ws


class MembershipTests(unittest.TestCase):
    def test_epic_selector_uses_project_types_and_components(self):
        cfg = base_cfg()
        self.assertEqual(
            workstreams.epic_selector_jql(cfg, component_ws()),
            'project = "APS" AND issuetype IN ("Epic") '
            'AND component IN ("Secure Data Exchange")',
        )

    def test_tagged_issue_selector_excludes_epics(self):
        cfg = base_cfg()
        self.assertEqual(
            workstreams.tagged_issue_selector_jql(cfg, component_ws()),
            'project = "APS" AND issuetype NOT IN ("Epic") '
            'AND component IN ("Secure Data Exchange")',
        )

    def test_child_work_includes_own_component_and_inherited(self):
        jql = workstreams.scope_jql(base_cfg(), component_ws(), "report")
        self.assertIn('project = "APS"', jql)
        self.assertIn('component IN ("Secure Data Exchange")', jql)
        self.assertIn("parentEpic IN (APS-10, APS-20)", jql)
        self.assertIn("parent IN (APS-30)", jql)
        self.assertIn('issuetype NOT IN ("Epic")', jql)
        self.assertIn("sprint in openSprints()", jql)

    def test_roadmap_scope_is_the_epics_only(self):
        jql = workstreams.scope_jql(base_cfg(), component_ws(), "roadmap")
        self.assertIn("key IN (APS-10, APS-20)", jql)
        self.assertNotIn("parentEpic", jql)
        self.assertIn("statusCategory != Done", jql)

    def test_lint_scope_includes_epics_and_everything_beneath(self):
        jql = workstreams.scope_jql(base_cfg(), component_ws(), "lint")
        self.assertIn("key IN (APS-10, APS-20)", jql)
        self.assertIn("parentEpic IN (APS-10, APS-20)", jql)
        self.assertNotIn("issuetype NOT IN", jql)

    def test_directly_tagged_work_is_found_when_no_epic_matches(self):
        ws = component_ws(_resolved_epic_keys=[], _resolved_tagged_keys=[])
        jql = workstreams.scope_jql(base_cfg(), ws, "report")
        self.assertIn('component IN ("Secure Data Exchange")', jql)
        self.assertNotIn("parentEpic", jql)

    def test_roadmap_is_skipped_when_no_epic_carries_the_component(self):
        ws = component_ws(_resolved_epic_keys=[])
        self.assertIsNone(workstreams.scope_jql(base_cfg(), ws, "roadmap"))

    def test_child_component_wins_restricts_inheritance(self):
        cfg = base_cfg(membership={"child_component_wins": True})
        jql = workstreams.scope_jql(cfg, component_ws(), "report")
        self.assertIn("component IS EMPTY", jql)

    def test_inheritance_can_be_turned_off(self):
        cfg = base_cfg(membership={"inherit_from_parent": False})
        jql = workstreams.scope_jql(cfg, component_ws(), "report")
        self.assertIn('component IN ("Secure Data Exchange")', jql)
        self.assertNotIn("parentEpic", jql)
        self.assertNotIn("parent IN", jql)

    def test_custom_epic_types(self):
        cfg = base_cfg(membership={"epic_types": ["Epic", "Feature"]})
        self.assertIn('issuetype IN ("Epic", "Feature")',
                      workstreams.epic_selector_jql(cfg, component_ws()))

    def test_workstream_project_overrides_the_default(self):
        ws = component_ws(project="ITK")
        self.assertIn('project = "ITK"',
                      workstreams.scope_jql(base_cfg(), ws, "report"))

    def test_component_names_with_quotes_are_escaped(self):
        ws = component_ws(components=['Say "hi"'])
        self.assertIn('component IN ("Say \\"hi\\"")',
                      workstreams.epic_selector_jql(base_cfg(), ws))

    def test_too_many_tagged_issues_skips_subtask_expansion(self):
        cfg = base_cfg(membership={"max_parent_keys": 2})
        ws = component_ws(_resolved_tagged_keys=["APS-1", "APS-2", "APS-3"])
        jql = workstreams.scope_jql(cfg, ws, "report")
        self.assertNotIn("parent IN", jql)
        self.assertIn("parentEpic IN", jql)


class ScopeTests(unittest.TestCase):
    def test_standup_window_comes_from_days(self):
        jql = workstreams.scope_jql(base_cfg(), component_ws(),
                                    "standup_moved", days=3)
        self.assertIn("updated >= -3d", jql)

    def test_workstream_scope_override_is_applied(self):
        ws = component_ws(scopes={"report": {"sprint": "any", "status": "open"}})
        jql = workstreams.scope_jql(base_cfg(), ws, "report")
        self.assertNotIn("openSprints", jql)
        self.assertIn("statusCategory != Done", jql)

    def test_global_scope_override_is_applied(self):
        cfg = base_cfg(scopes={"ready": {"sprint": "future", "status": "any"}})
        jql = workstreams.scope_jql(cfg, component_ws(), "ready")
        self.assertIn("futureSprints", jql)
        self.assertNotIn("statusCategory", jql)


class DiscoveryTests(unittest.TestCase):
    def test_discovery_queries_are_cached_per_workstream(self):
        cfg = base_cfg()
        ws = component_ws()
        ws.pop("_resolved_epic_keys")
        ws.pop("_resolved_tagged_keys")
        with patch("core.workstreams.sources.fetch_jira_keys",
                   return_value=["APS-10"]) as fetch:
            workstreams.scope_jql(cfg, ws, "report")
            workstreams.scope_jql(cfg, ws, "roadmap")
            workstreams.scope_jql(cfg, ws, "lint")
            # One epic query plus one tagged-issue query, then cached.
            self.assertEqual(fetch.call_count, 2)


class LegacyConfigTests(unittest.TestCase):
    def test_direct_jql_workstream_is_unchanged(self):
        cfg = base_cfg()
        cfg["jira"].pop("project")
        ws = {"abbrev": "OLD",
              "jira_jql": "project = OLD AND sprint in openSprints()"}
        self.assertEqual(workstreams.scope_jql(cfg, ws, "report"),
                         "project = OLD AND sprint in openSprints()")

    def test_direct_jql_keeps_its_fallback_fields(self):
        cfg = base_cfg()
        cfg["jira"].pop("project")
        ws = {"abbrev": "OLD", "lint_jql": "project = OLD"}
        self.assertEqual(workstreams.scope_jql(cfg, ws, "review"),
                         "project = OLD")

    def test_direct_jql_days_placeholder(self):
        cfg = base_cfg()
        cfg["jira"].pop("project")
        ws = {"abbrev": "OLD", "standup_moved_jql": "updated >= -{days}d"}
        self.assertEqual(
            workstreams.scope_jql(cfg, ws, "standup_moved", days=5),
            "updated >= -5d")

    def test_old_epic_component_keys_still_resolve(self):
        cfg = base_cfg()
        cfg["jira"].pop("project")
        ws = {"abbrev": "SDX", "jira_project": "APS",
              "epic_components": ["Secure Data Exchange"],
              "lint_jql": "statusCategory != Done",
              "_resolved_epic_keys": ["APS-10"],
              "_resolved_tagged_keys": []}
        jql = workstreams.scope_jql(cfg, ws, "lint")
        self.assertIn('project = "APS"', jql)
        self.assertIn("key IN (APS-10)", jql)
        self.assertIn("statusCategory != Done", jql)


class InheritedComponentCheckTests(unittest.TestCase):
    """Child work must not be nagged for a Component it inherits."""

    LINT_CFG = {
        "required_fields": ["component", "epic"],
        "require_acceptance_criteria": False,
        "require_estimate": False,
        "min_title_words": 3,
        "vague_title_terms": [],
    }

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
        findings = lint.check_issue(self._issue(), self.LINT_CFG,
                                    component_inherited=True)
        self.assertNotIn("missing-component", {f["rule"] for f in findings})

    def test_missing_component_still_flagged_for_legacy_workstreams(self):
        findings = lint.check_issue(self._issue(), self.LINT_CFG,
                                    component_inherited=False)
        self.assertIn("missing-component", {f["rule"] for f in findings})

    def test_ready_component_criterion_does_not_fail_inherited_child(self):
        verdict = ready.evaluate_issue(self._issue(), self.LINT_CFG,
                                       blocking={"has-component"},
                                       deep_findings=None,
                                       component_inherited=True)
        self.assertTrue(verdict["ready"])

    def test_component_scope_detection(self):
        self.assertTrue(
            workstreams.uses_component_scope(base_cfg(), component_ws()))
        self.assertFalse(
            workstreams.uses_component_scope(base_cfg(),
                                             {"abbrev": "X", "jira_jql": "x"}))


if __name__ == "__main__":
    unittest.main()
