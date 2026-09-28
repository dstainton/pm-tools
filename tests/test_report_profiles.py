"""Role profiles, report shape, briefs, planning, and sprint review."""

import datetime as dt
import unittest
from argparse import Namespace

from commands import brief, metrics, ready
from core import audience, metrics as core_metrics, report_profiles, report_render


def _cfg(role=None):
    cfg = {
        "products": [
            {"name": "Integration Platform", "abbrev": "IP",
             "product_goal": "Ship the exchange"},
            {"name": "Portal", "abbrev": "PORTAL",
             "product_goal": "A clearer portal"},
        ],
        "output": {"file": "weekly_report_{date}.md",
                   "state_file": "report_state.json", "directory": "."},
        "audiences": {"partner": {"show_backlog_percent": False}},
    }
    if role:
        cfg["role"] = role
    return cfg


def _epic(key, summary, signal="On track", blocked=0, due="", items=None):
    return {
        "key": key,
        "summary": summary,
        "status": "In progress",
        "status_category": "indeterminate",
        "signal": signal,
        "signal_reason": "1 blocked" if blocked else "",
        "blocked": blocked,
        "due": due,
        "children_done": 1,
        "children_total": 4,
        "url": f"https://example.test/browse/{key}",
        "items": items or [],
        "moved": [],
    }


def _rows():
    sdx = {"name": "Secure Data Exchange", "abbrev": "SDX"}
    portal = {"name": "Public site", "abbrev": "WEB"}
    ip = {"name": "Integration Platform", "abbrev": "IP",
          "product_goal": "Ship the exchange"}
    other = {"name": "Portal", "abbrev": "PORTAL",
             "product_goal": "A clearer portal"}
    decision = {
        "type": "decision",
        "name": "Decisions",
        "partner_visible": True,
        "root": {"url": "https://example.test/d"},
        "entries": [{
            "title": "Certificate rotation cadence",
            "change": "new",
            "status": "Waiting",
            "url": "https://example.test/dec",
            "fields": {"Needed from": "partner"},
            "summary": "Agree the cadence.",
        }],
    }
    adr = {
        "type": "adr",
        "name": "ADRs",
        "root": {"url": "https://example.test/adr"},
        "scope": {"workstream": "SDX"},
        "entries": [{
            "title": "Store tokens in the HSM",
            "change": "new",
            "status": "Accepted",
            "url": "https://example.test/adr1",
            "summary": "Keys stay in the module.",
        }],
    }
    risk = {
        "type": "risk",
        "name": "Risks",
        "root": {"url": "https://example.test/r"},
        "entries": [{
            "title": "HSM capacity",
            "change": "new",
            "high": True,
            "status": "Open",
            "url": "https://example.test/risk",
            "summary": "Capacity during rotation.",
        }],
    }
    page = {
        "source": "Confluence",
        "title": "Service blueprint",
        "kind": "blueprint",
        "type": "page",
        "updated": "2026-09-20",
        "updated_by": "Dana",
        "url": "https://example.test/blueprint",
        "summary": "The exchange journey.",
    }
    req = {
        "source": "Confluence",
        "title": "Export requirements",
        "kind": "requirement",
        "type": "page",
        "updated": "2026-09-20",
        "url": "https://example.test/req",
        "summary": "What the export must do.",
    }
    sdx_row = {
        "epics": [_epic("APS-1", "Secure exchange", signal="At risk", blocked=1,
                        due="2026-09-20", items=[{
                            "key": "APS-10", "summary": "Rotate certificates",
                            "status": "Blocked", "issuetype": "Story",
                            "assignee": "A. Lee", "updated": "2026-09-20",
                            "url": "https://example.test/APS-10",
                        }])],
        "items": [page, req],
        "registers": [decision, adr, risk],
        "changed": [],
    }
    web_row = {
        "epics": [_epic("APS-2", "Portal launch", due="2026-10-01")],
        "items": [],
        "registers": [decision, adr, risk],
        "changed": [],
    }
    groups = [(ip, [sdx]), (other, [portal])]
    rows = [(sdx, sdx_row), (portal, web_row)]
    sections = [
        (sdx, "### Changed\n- Certificates moved. [APS-10]\n"),
        (portal, "### Changed\n- Copy updated.\n"),
    ]
    window = {"label": "since 15 Sep", "start": dt.date(2026, 9, 15)}
    return groups, rows, sections, window


class ProfileResolutionTests(unittest.TestCase):
    def test_no_role_stays_product_management(self):
        self.assertEqual(report_profiles.resolve({}, Namespace(audience=None)), "pm")
        self.assertEqual(report_profiles.privacy("pm"), "pm")

    def test_each_role_has_its_own_profile_and_file(self):
        cfg = _cfg()
        for role in ("analyst", "developer", "service-designer"):
            cfg["role"] = role
            self.assertEqual(report_profiles.resolve(cfg, Namespace(audience=None)), role)
            self.assertEqual(report_profiles.privacy(role), "work")
            self.assertNotEqual(
                audience.state_path(cfg, role, None),
                audience.state_path(cfg, "work", None))
            self.assertNotEqual(
                audience.output_name(cfg, role, "2026-09-28"),
                audience.output_name(cfg, "pm", "2026-09-28"))

    def test_audience_override_wins_and_work_stays_generic(self):
        cfg = _cfg("service-designer")
        self.assertEqual(
            report_profiles.resolve(cfg, Namespace(audience="leadership")), "leadership")
        self.assertEqual(
            report_profiles.resolve(cfg, Namespace(audience="work")), "work")
        self.assertEqual(report_profiles.display_name(cfg, "work"), "Team")
        self.assertEqual(
            report_profiles.display_name(cfg, "service-designer"), "Service designer")


class ReportShapeTests(unittest.TestCase):
    def setUp(self):
        self.groups, self.rows, self.sections, self.window = _rows()

    def _render(self, who, sources="compact"):
        return report_render.render_pm(
            _cfg(), self.groups, self.rows, self.sections, self.window, "",
            who=who, sources=sources)

    def test_pm_opens_on_attention_and_skips_the_full_source_table(self):
        text = self._render("pm")
        self.assertTrue(text.splitlines()[3].startswith("## Needs attention")
                        or "## Needs attention" in text.split("## At a glance")[0])
        self.assertLess(text.index("## Needs attention"), text.index("## At a glance"))
        self.assertIn("Active Epics", text)
        self.assertNotIn("Items in window", text)
        self.assertIn("APS-1", text)
        self.assertIn("Product Goal: Ship the exchange", text)
        self.assertNotIn("Definition of Done", text)
        self.assertNotIn("| Assignee |", text)
        self.assertIn("pm report --sources full", text)
        self.assertIn("A. Lee", text)

    def test_full_sources_keep_the_table(self):
        text = self._render("pm", sources="full")
        self.assertIn("| Assignee |", text)
        self.assertIn("APS-10", text)

    def test_internal_roles_do_not_share_one_report(self):
        analyst = self._render("analyst")
        developer = self._render("developer")
        designer = self._render("service-designer")
        self.assertIn("Business analyst", analyst)
        self.assertIn("Developer", developer)
        self.assertIn("Service designer", designer)
        self.assertNotIn("A. Lee", analyst)
        self.assertNotIn("Dana", designer)
        self.assertLess(designer.index("Service blueprint"), designer.index("#### Epics"))
        self.assertIn("Store tokens in the HSM", developer)
        self.assertIn("Export requirements", analyst)
        self.assertNotIn("Delivery pulse", analyst)
        self.assertNotIn("Delivery pulse", designer)
        for text in (analyst, developer, designer):
            self.assertNotIn("| Assignee |", text)

    def test_partner_status_is_not_a_bare_percentage(self):
        product = {"name": "Integration Platform", "abbrev": "IP"}
        ws = {"name": "Secure Data Exchange", "abbrev": "SDX", "partner_visible": True}
        epic = _epic("APS-1", "Secure exchange")
        epic["labels"] = ["partner-visible"]
        text = report_render.render_partner(
            _cfg(), [(product, [ws])], [(ws, {"epics": [epic], "items": [],
                                              "registers": self.rows[0][1]["registers"]})],
            ["### What's new\n- Secure exchange is in progress.\n"],
            self.window)
        self.assertIn("In progress", text)
        self.assertIn("1 of 4", text)
        self.assertNotIn("| 25% |", text)
        self.assertIn("Input needed", text)
        self.assertIn("Certificate rotation cadence", text)
        self.assertNotIn("A. Lee", text)

    def test_leadership_keeps_the_goal_and_no_names(self):
        product = self.groups[0][0]
        ws = self.groups[0][1][0]
        text = report_render.render_leadership(
            _cfg(), [(product, [ws])], [self.rows[0]],
            ["### Headline\n- On track.\n### Decisions needed\n- Nothing this period.\n"
             "### Risks to watch\n- Capacity.\n"],
            self.window)
        self.assertIn("Product Goal: Ship the exchange", text)
        self.assertIn("### Headline", text)
        self.assertNotIn("A. Lee", text)
        self.assertNotIn("Dana", text)


class BriefTests(unittest.TestCase):
    def test_design_review_includes_changed_service_documentation(self):
        section = {
            "product": {"name": "Integration Platform", "abbrev": "IP",
                        "product_goal": "Ship it"},
            "change": "- Blueprint updated.",
            "issues": [],
            "needs": [],
            "risks": [],
            "pages": [{
                "title": "Service blueprint",
                "url": "https://example.test/blueprint",
                "kind": "blueprint",
                "summary": "The exchange journey.",
            }],
            "registers": [],
        }
        text = brief.render_prep(
            "Design review", [section], "2026-09-01", "service-designer", cfg=_cfg())
        self.assertIn("Changed service documentation", text)
        self.assertIn("Service blueprint", text)
        self.assertIn("https://example.test/blueprint", text)


class PlanningAndSprintTests(unittest.TestCase):
    def test_plan_groups_ready_work_and_does_not_commit_a_sprint(self):
        ws = {"abbrev": "SDX", "name": "Secure Data Exchange"}
        verdicts = [
            {"key": "APS-10", "title": "Rotate", "ready": True, "failed": []},
            {"key": "APS-11", "title": "Export", "ready": False,
             "failed": [{"reason": "No acceptance criteria"}]},
        ]
        issues = [
            {"key": "APS-10", "epic": "APS-1", "story_points": 3, "summary": "Rotate"},
            {"key": "APS-11", "epic": "APS-1", "story_points": 5, "summary": "Export",
             "status": "Blocked", "labels": ["blocked"]},
        ]
        text = ready.render_plan(
            {}, [(ws, verdicts, issues)],
            [{"workstream": "SDX", "weekly_rate": 4.0}])
        self.assertIn("Ready to plan: 1", text)
        self.assertIn("Needs refinement", text)
        self.assertIn("No acceptance criteria", text)
        self.assertIn("APS-1", text)
        self.assertIn("not a Sprint commitment", text)
        self.assertIn("4.0", text)

    def test_sprint_snapshot_lists_finished_and_unfinished_work(self):
        sprint = {"name": "Sprint 12", "goal": "Ship export",
                  "start": "2026-09-01T00:00:00.000+0000", "id": 1}
        done = {
            "key": "APS-10", "summary": "Rotate", "story_points": 3,
            "status": "Done", "status_category": "done", "issuetype": "Story",
            "updated": "2026-09-10T00:00:00.000+0000",
            "created": "2026-08-01T00:00:00.000+0000",
            "epic": "APS-1",
        }
        open_item = {
            "key": "APS-11", "summary": "Export", "story_points": 5,
            "status_category": "indeterminate", "issuetype": "Story",
            "created": "2026-08-01T00:00:00.000+0000",
            "epic": "APS-1",
        }
        snap = core_metrics.sprint_snapshot([done, open_item], sprint)
        self.assertIn("completed", snap)
        self.assertIn("unfinished", snap)
        self.assertEqual(snap["goal"], "Ship export")
        text = metrics.render_sprint("Sprint 12", [({"name": "IP", "abbrev": "IP"}, [dict(snap, workstream="SDX")])])
        self.assertIn("Sprint Goal: Ship export", text)
        self.assertIn("Completed", text)
        self.assertIn("Incomplete", text)
        self.assertIn("Forecast at start", text)


if __name__ == "__main__":
    unittest.main()
