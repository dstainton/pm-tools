"""Report shapes, role resolution, and name omission."""

import datetime as dt
import tempfile
import unittest
from argparse import Namespace
from unittest.mock import patch

from commands import brief, metrics
from core import audience, comments, config, model, report_render


class ShapeTests(unittest.TestCase):
    def test_role_wins_over_the_saved_default(self):
        cfg = {"role": "service-designer", "audiences": {"default": "pm"}}
        self.assertEqual(audience.resolve_shape(cfg, Namespace(audience=None)), "work")
        self.assertEqual(
            audience.resolve_shape(cfg, Namespace(audience="leadership")), "leadership")

    def test_a_missing_role_uses_the_saved_default(self):
        cfg = {"audiences": {"default": "leadership"}}
        self.assertEqual(audience.resolve_shape(cfg, Namespace(audience=None)), "leadership")
        self.assertEqual(audience.resolve_shape({}, Namespace(audience=None)), "pm")

    def test_only_pm_names_people(self):
        self.assertTrue(audience.names_people("pm"))
        for shape in ("work", "leadership", "partner"):
            self.assertFalse(audience.names_people(shape))

    def test_work_has_its_own_file(self):
        cfg = {"output": {"file": "weekly_report_{date}.md",
                          "state_file": "report_state.json", "directory": "."}}
        self.assertEqual(audience.output_name(cfg, "work", "2026-09-28"),
                         "weekly_report_work_2026-09-28.md")
        self.assertTrue(audience.state_path(cfg, "work", None).endswith(
            "report_state_work.json"))

    def test_a_bad_role_is_rejected(self):
        with self.assertRaises(SystemExit) as caught:
            config._validate_role({"role": "boss"})
        self.assertIn("role", str(caught.exception))

    def test_me_summary_must_be_a_sprint_or_a_day_count(self):
        config._validate_me({"me": {"summary": "sprint"}})
        config._validate_me({"me": {"summary": 14}})
        with self.assertRaises(SystemExit):
            config._validate_me({"me": {"summary": 0}})


class NameTests(unittest.TestCase):
    def test_a_comment_line_drops_the_author(self):
        line = comments.format_line({
            "created": "2026-09-22T12:00:00.000+0000",
            "author": {"displayName": "Dana"},
            "body": "the excerpt",
        }, 200, author=False)
        self.assertEqual(line, "2026-09-22: the excerpt")
        self.assertNotIn("Dana", line)

    def test_leadership_and_partner_omit_the_decision_owner(self):
        record = {
            "name": "Decisions",
            "partner_visible": True,
            "root": {"url": "https://example.test/d", "updated_by": "Dana"},
            "entries": [{
                "title": "Export",
                "change": "changed",
                "url": "https://example.test/e",
                "fields": {"Owner": "A. Lee"},
                "summary": "Agreed.",
            }],
        }
        for level in ("leadership", "partner"):
            text = report_render.register_block(record, level, {"since": "2026-09-01"})
            self.assertNotIn("A. Lee", text)
            self.assertNotIn("Dana", text)
            self.assertIn("Export", text)

    def test_the_assignee_line_is_left_out_of_the_prompt(self):
        lines = model._item_line(
            {"key": "APS-2", "issuetype": "Story", "summary": "Export",
             "status": "Doing", "assignee": "A. Lee"},
            names=False)
        self.assertNotIn("Assignee", "\n".join(lines))
        self.assertNotIn("A. Lee", "\n".join(lines))

    def test_work_keeps_epic_sections_and_drops_the_assignee_column(self):
        cfg = {"products": [{"name": "Integration Platform", "abbrev": "IP"}]}
        ws = {"name": "Secure Data Exchange", "abbrev": "SDX"}
        product = {"name": "Integration Platform", "abbrev": "IP"}
        row = {
            "epics": [{
                "key": "APS-1",
                "summary": "Export",
                "items": [{
                    "key": "APS-2",
                    "summary": "Do the export",
                    "assignee": "A. Lee",
                    "status": "Doing",
                    "issuetype": "Story",
                    "updated": "2026-09-20",
                    "url": "https://example.test/APS-2",
                }],
            }],
            "items": [{
                "source": "Confluence",
                "title": "Blueprint",
                "updated": "2026-09-20",
                "updated_by": "Dana",
                "type": "page",
                "url": "https://example.test/p",
            }],
        }
        text = report_render.render_pm(
            cfg, [(product, [ws])], [(ws, row)], [(ws, "The section.")],
            {"label": "Sprint 139", "start": dt.date(2026, 9, 15)},
            "", who="work")
        self.assertIn("APS-1", text)
        self.assertIn("Epics", text)
        self.assertNotIn("Assignee", text)
        self.assertNotIn("A. Lee", text)
        self.assertNotIn("Dana", text)
        self.assertIn("Team", text)

    def test_partner_redaction_still_removes_a_name_the_model_wrote(self):
        line = comments.format_line({
            "created": "2026-09-22T12:00:00.000+0000",
            "author": {"displayName": "Dana"},
            "body": "the excerpt",
        }, 200, author=False)
        prose = line + "\nA. Lee approved the export."
        text, removed = audience.redact(prose, ["A. Lee", "Dana"], set())
        self.assertIn("the excerpt", text)
        self.assertNotIn("A. Lee", text)
        self.assertEqual(removed, 1)


class BriefAndMetricsTests(unittest.TestCase):
    def test_a_saved_meeting_depth_wins_over_role(self):
        cfg = {"role": "service-designer"}
        saved = brief.prep_level(cfg, Namespace(audience=None),
                                  {"_audience_level": "leadership"})
        self.assertEqual(saved, "leadership")
        fresh = brief.prep_level(cfg, Namespace(audience=None), None)
        self.assertEqual(fresh, "work")
        forced = brief.prep_level(cfg, Namespace(audience="pm"), None)
        self.assertEqual(forced, "pm")

    def test_work_metrics_are_the_full_tables_and_partner_exits(self):
        cfg = {"jira": {"project": "APS"}, "workstreams": []}
        with tempfile.TemporaryDirectory() as folder:
            args = Namespace(audience="work", sprint=None, weeks=None, json=False,
                             out=folder, since=None, days=None)
            with patch("commands.metrics.gather", return_value=[]), \
                    patch("commands.metrics.render", return_value="FULL") as full, \
                    patch("commands.metrics.render_headline", return_value="HEAD") as head:
                metrics.run(cfg, args)
            full.assert_called()
            head.assert_not_called()
        partner = Namespace(audience="partner", sprint=None, weeks=None, json=False,
                            out=None, since=None, days=None)
        with self.assertRaises(SystemExit) as caught:
            metrics.run(cfg, partner)
        self.assertIn("partner", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
