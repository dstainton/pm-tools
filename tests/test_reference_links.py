"""Every Jira issue and Confluence page a report names is a link."""

import datetime as dt
import unittest

from commands import brief, me, metrics, ready, review
from core import citations, dependencies, report_profiles, report_render
from tests.test_report_profiles import _cfg as _profile_cfg, _rows


BASE = "https://example.atlassian.net"


class CitationTests(unittest.TestCase):
    def setUp(self):
        self.cmap = {
            "APS-10": ("APS-10", f"{BASE}/browse/APS-10"),
            "D1": ("Decision: rotation", "https://example/pages/1001"),
        }

    def test_a_bare_key_in_the_material_becomes_a_link(self):
        self.assertEqual(
            citations.link_keys("See APS-10 for the work.", self.cmap),
            f"See [APS-10]({BASE}/browse/APS-10) for the work.")

    def test_unknown_keys_and_existing_links_stay(self):
        text = (f"[APS-10]({BASE}/browse/APS-10) and APS-99, "
                f"{BASE}/browse/APS-10 and `APS-10`.")
        self.assertEqual(citations.link_keys(text, self.cmap), text)


class WeeklyReportTests(unittest.TestCase):
    def test_needs_attention_links_the_epic_and_the_register_page(self):
        groups, rows, _sections, _window = _rows()
        lines = report_render.needs_attention(
            groups, rows, report_profiles.get("pm"), today=dt.date(2026, 9, 28))
        text = "\n".join(lines)
        self.assertIn("[APS-1](https://example.test/browse/APS-1) Secure exchange (SDX)", text)
        self.assertIn("Decision needed: [Certificate rotation cadence](https://example.test/dec)", text)
        self.assertIn("Risk (high): [HSM capacity](https://example.test/risk)", text)

    def test_service_documentation_is_linked(self):
        groups, rows, _sections, _window = _rows()
        lines = report_render.needs_attention(
            groups, rows, report_profiles.get("service-designer"),
            today=dt.date(2026, 9, 28))
        self.assertIn(
            "- Service documentation changed: [Service blueprint](https://example.test/blueprint)",
            lines)

    def test_blocker_lines_link_both_issues(self):
        rows = [{
            "key": "APS-10", "url": f"{BASE}/browse/APS-10", "summary": "Rotate",
            "blocked_by": [{"key": "OPS-4", "summary": "HSM order",
                            "url": f"{BASE}/browse/OPS-4"}],
            "blocks": [{"key": "APS-12", "summary": "", "url": f"{BASE}/browse/APS-12"}],
        }]
        lines = dependencies.lines_for(rows, {"APS-10", "APS-12"})
        self.assertEqual(lines, [
            f"- [APS-10]({BASE}/browse/APS-10) is blocked by "
            f"[OPS-4]({BASE}/browse/OPS-4) HSM order (outside this report)",
            f"- [APS-10]({BASE}/browse/APS-10) blocks [APS-12]({BASE}/browse/APS-12)",
        ])

    def test_partner_input_follows_the_partner_link_setting(self):
        groups, rows, _sections, window = _rows()
        product = {"name": "Integration Platform", "abbrev": "IP"}
        ws = {"name": "Secure Data Exchange", "abbrev": "SDX", "partner_visible": True}
        epic = dict(rows[0][1]["epics"][0], labels=["partner-visible"])
        data = [(ws, {"epics": [epic], "items": [], "registers": rows[0][1]["registers"]})]
        cfg = _profile_cfg()
        text = report_render.render_partner(cfg, [(product, [ws])], data, [""], window)
        self.assertIn("- Certificate rotation cadence", text)
        self.assertNotIn("https://example.test/dec", text)
        cfg["audiences"]["partner"]["include_confluence_links"] = True
        text = report_render.render_partner(cfg, [(product, [ws])], data, [""], window)
        self.assertIn("- [Certificate rotation cadence](https://example.test/dec)", text)


class CommandMarkdownTests(unittest.TestCase):
    def test_me_links_issues_and_epic_headings(self):
        cfg = {"jira": {"project": "APS", "base_url": BASE},
               "workstreams": [{"name": "Secure Data Exchange", "abbrev": "SDX",
                                "components": ["Secure Data Exchange"]}]}
        issue = {"key": "APS-2", "summary": "In the stream", "status": "In Progress",
                 "status_category": "indeterminate", "issuetype": "Story",
                 "components": ["Secure Data Exchange"], "epic": "APS-1",
                 "url": f"{BASE}/browse/APS-2",
                 "updated": "2026-09-27T00:00:00.000+0000", "labels": []}
        text = me.render_snapshot(cfg, [issue], None, dt.date(2026, 9, 28), None)
        self.assertIn(f"### [APS-1]({BASE}/browse/APS-1)", text)
        self.assertIn(f"- [APS-2]({BASE}/browse/APS-2) — In the stream", text)
        window = {"start": dt.date(2026, 9, 20), "label": "last 8 days"}
        text = me.render_summary(cfg, [issue], [], None, window, dt.date(2026, 9, 28))
        self.assertIn(f"- [APS-2]({BASE}/browse/APS-2) — In the stream (In Progress)", text)

    def test_ready_plan_links_items_and_epics(self):
        ws = {"abbrev": "SDX", "name": "Secure Data Exchange"}
        verdicts = [{"key": "APS-10", "title": "Rotate", "ready": True, "failed": [],
                     "url": f"{BASE}/browse/APS-10"}]
        issues = [{"key": "APS-10", "epic": "APS-1", "story_points": 3}]
        text = ready.render_plan({"jira": {"base_url": BASE}}, [(ws, verdicts, issues)])
        self.assertIn(f"**[APS-1]({BASE}/browse/APS-1)** (SDX)", text)
        self.assertIn(f"- [APS-10]({BASE}/browse/APS-10) Rotate, 3 pt", text)

    def test_ready_report_links_ready_items(self):
        ws = {"abbrev": "SDX", "name": "Secure Data Exchange"}
        verdict = {"key": "APS-10", "title": "Rotate", "type": "Story", "ready": True,
                   "failed": [], "advisory": [], "url": f"{BASE}/browse/APS-10"}
        text = ready.build_markdown({}, [(ws, [verdict])], deep=False)
        self.assertIn(f"- **[APS-10]({BASE}/browse/APS-10)**: Rotate", text)

    def test_sprint_review_links_cards_and_epics(self):
        snap = {"workstream": "SDX", "forecast": 3, "done": 3, "added_points": 0,
                "carried": 0, "carried_out": [], "goal": "",
                "epics": ["APS-1"],
                "completed": [{"key": "APS-10", "summary": "Rotate",
                               "url": f"{BASE}/browse/APS-10"}],
                "unfinished": []}
        text = metrics.render_sprint(
            "Sprint 12", [({"name": "IP", "abbrev": "IP"}, [snap])], cfg={})
        self.assertIn(f"- [APS-1]({BASE}/browse/APS-1)", text)
        self.assertIn(f"- [APS-10]({BASE}/browse/APS-10) Rotate", text)

    def test_brief_links_change_tags_and_epics(self):
        section = {
            "product": {"name": "Integration Platform", "abbrev": "IP"},
            "change": "New this week:\n  - [APS-10] APS-10: Rotate\n  - [APS-77] Gone",
            "issues": [{"key": "APS-10", "url": f"{BASE}/browse/APS-10"}],
            "needs": [], "risks": [], "pages": [], "registers": [],
            "epics": [{"key": "APS-1", "summary": "Secure exchange", "status": "In progress",
                       "signal": "At risk", "children_done": 1, "children_total": 4}],
        }
        cfg = {"jira": {"base_url": BASE}}
        text = brief.render_prep("Standup", [section], None, "pm", cfg=cfg)
        self.assertIn(f"[APS-10]({BASE}/browse/APS-10) APS-10: Rotate", text)
        self.assertIn(f"[APS-77]({BASE}/browse/APS-77) Gone", text)
        text = brief.render_prep("Board", [section], None, "leadership", cfg=cfg)
        self.assertIn(f"| [APS-1]({BASE}/browse/APS-1) Secure exchange |", text)
        self.assertIn(f"- [APS-1]({BASE}/browse/APS-1) Secure exchange is at risk.", text)

    def test_review_heading_is_the_linked_key(self):
        ws = {"abbrev": "SDX", "name": "Secure Data Exchange"}
        finding = {"key": "APS-11", "aspect": "titles", "problem": "Vague", "detail": "Say what"}
        lookup = {"APS-11": {"summary": "Fix stuff", "url": f"{BASE}/browse/APS-11"}}
        text = review.build_markdown({}, "titles", [(ws, [finding], lookup)], False)
        self.assertIn(f"### [APS-11]({BASE}/browse/APS-11): Fix stuff", text)
        self.assertNotIn("Open in Jira", text)


if __name__ == "__main__":
    unittest.main()
