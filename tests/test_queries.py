"""Query registry: defaults match today's JQL, and overrides fail closed."""

import unittest

from core import filters, queries, workstreams


def _cfg(extra=None, ws=None):
    cfg = {
        "jira": {"project": "APS"},
        "membership": {},
        "queries": extra or {},
        "workstreams": [ws or {
            "name": "Secure Data Exchange", "abbrev": "SDX",
            "components": ["Secure Data Exchange"], "project": "APS",
        }],
    }
    queries.validate_config(cfg)
    return cfg


class RenderTests(unittest.TestCase):
    def test_named_queries_match_todays_strings(self):
        self.assertEqual(
            queries.render(None, "coverage.open_in_project", project="APS"),
            'project = "APS" AND statusCategory != Done')
        self.assertEqual(
            queries.render(None, "today.in_sprint_open", project="APS"),
            'project = "APS" AND sprint in openSprints() AND statusCategory != Done')
        self.assertEqual(
            queries.render(None, "release_notes.since", since="2026-08-01"),
            'resolved >= "2026-08-01"')
        self.assertEqual(
            queries.render(None, "release_notes.version", version="2026.9"),
            'fixVersion = "2026.9"')
        self.assertEqual(
            queries.render(None, "confluence.window", cql="space = \"SDX\"", since="2026-06-01"),
            "(space = \"SDX\") AND lastmodified >= '2026-06-01'")
        self.assertEqual(
            queries.render(None, "doctor.membership_open", base="project = \"APS\""),
            '(project = "APS") AND (statusCategory != Done)')
        self.assertEqual(
            queries.render(None, "membership.anchor.component", values=["Secure Data Exchange"]),
            'component IN ("Secure Data Exchange")')
        self.assertEqual(
            queries.render(None, "membership.inherit.epic", epic_keys=["APS-1"]),
            "parentEpic IN (APS-1)")

    def test_added_status_is_a_valid_scope_choice(self):
        cfg = _cfg({"status.review": {"text": 'status = "In Review"'}})
        clause = filters.compile_scope({"status": "review"}, cfg)
        self.assertEqual(clause, 'status = "In Review"')
        with self.assertRaises(SystemExit) as caught:
            filters.compile_scope({"status": "nope"}, cfg)
        self.assertIn("review", str(caught.exception))

    def test_any_and_cycles_are_rejected(self):
        with self.assertRaises(SystemExit) as caught:
            queries.validate_config({"queries": {"status.any": {"text": "x"}}})
        self.assertIn("any", str(caught.exception))
        with self.assertRaises(SystemExit) as caught:
            queries.validate_config({"queries": {"status.review": {"text": "{status_open}"}}})
        self.assertIn("cycle", str(caught.exception))

    def test_label_and_field_modes(self):
        cfg = _cfg(ws={
            "name": "Secure Data Exchange", "abbrev": "SDX",
            "labels": ["sdx"], "project": "APS",
        })
        cfg["membership"] = {"by": "label"}
        self.assertIn('labels IN ("sdx")', workstreams.epic_selector_jql(cfg, cfg["workstreams"][0]))
        with self.assertRaises(SystemExit) as caught:
            from core import config
            config._validate_membership({"membership": {
                "by": "label", "child_component_wins": True}})
        self.assertIn("label", str(caught.exception))

        cfg = _cfg(ws={
            "name": "Secure Data Exchange", "abbrev": "SDX",
            "field_values": ["SDX"], "project": "APS",
        })
        cfg["membership"] = {"by": "field", "field": "cf[10050]"}
        self.assertIn('cf[10050] IN ("SDX")',
                      workstreams.epic_selector_jql(cfg, cfg["workstreams"][0]))

    def test_inherit_override_must_keep_its_placeholder(self):
        cfg = _cfg({"membership.inherit.epic": {"text": '"Epic Link" IN ({epic_keys})'}})
        self.assertEqual(
            queries.render(cfg, "membership.inherit.epic", epic_keys=["APS-1"]),
            '"Epic Link" IN (APS-1)')
        with self.assertRaises(SystemExit):
            queries.validate_config({"queries": {"membership.inherit.epic": {"text": "parent = APS-1"}}})

    def test_bad_key_and_date_raise(self):
        with self.assertRaises(ValueError):
            queries.render(None, "membership.inherit.epic", epic_keys=["nope"])
        with self.assertRaises(ValueError):
            queries.render(None, "release_notes.since", since="August")


if __name__ == "__main__":
    unittest.main()
