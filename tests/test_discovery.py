"""Phase 2A discovery: read-only configured facts, selection and rendering."""
import argparse
import os
import tempfile
import unittest
from unittest.mock import patch

from commands import discover
from core import discovery


CFG = {
    "jira": {"project": "APS"},
    "products": [
        {"name": "Platform", "abbrev": "PLAT", "project": "APS",
         "product_goal": "Enable integration"},
        {"name": "Other", "abbrev": "OTHER", "project": "NEXT"}],
    "workstreams": [
        {"name": "Gateway", "abbrev": "GW", "product": "PLAT",
         "components": ["Gateway"]},
        {"name": "Service", "abbrev": "SVC", "product": "OTHER",
         "components": ["Service"]},
        {"name": "Unassigned Docs", "abbrev": "DOC",
         "components": ["Documentation"]}],
}


class DiscoveryTests(unittest.TestCase):
    def test_config_identity_and_unknowns_do_not_become_inference(self):
        result = discovery.inspect(CFG)
        self.assertEqual([p["abbrev"] for p in result["products"]],
                         ["PLAT", "OTHER", "UNASSIGNED"])
        self.assertEqual([w["abbrev"] for w in result["workstreams"]],
                         ["GW", "SVC", "DOC"])
        self.assertEqual(result["workstreams"][0]["project"], "APS")
        self.assertEqual(result["workstreams"][0]["project_origin"], "product")
        self.assertEqual(result["workstreams"][2]["project_origin"], "Jira default")
        self.assertEqual(result["workstreams"][0]["anchors"], ["Gateway"])
        self.assertIn("responsibilities", result["workstreams"][0]["gaps"])
        self.assertIsNone(result["products"][1]["goal"])
        self.assertTrue(result["products"][2]["implicit"])

    def test_project_filter_preserves_only_matching_entities(self):
        result = discovery.inspect(CFG, project="NEXT")
        self.assertEqual([w["abbrev"] for w in result["workstreams"]], ["SVC"])
        self.assertEqual([p["abbrev"] for p in result["products"]], ["OTHER"])

    def test_explicit_selection_and_legacy_jql(self):
        ws = {"name": "Old", "abbrev": "OLD", "jira_jql": "project = APS"}
        result = discovery.inspect(dict(CFG, workstreams=[ws]), selected=[ws])
        self.assertEqual([p["abbrev"] for p in result["products"]], ["UNASSIGNED"])
        self.assertTrue(result["workstreams"][0]["legacy_jql_configured"])
        self.assertIn("legacy JQL configured", discovery.markdown(result))

    def test_no_products_produces_unassigned_not_a_fabricated_product(self):
        cfg = {"jira": {"project": "ONE"}, "workstreams": [{
            "name": "Stream", "abbrev": "S", "components": ["One"]}]}
        result = discovery.inspect(cfg)
        self.assertEqual(result["products"][0]["abbrev"], "UNASSIGNED")
        self.assertTrue(result["products"][0]["implicit"])
        self.assertIn("not a confirmed product", discovery.markdown(result))

    def test_filtered_out_config_reports_absence_explicitly(self):
        result = discovery.inspect(CFG, project="MISSING")
        self.assertEqual(result["products"], [])
        self.assertIn("No configured profiles", discovery.markdown(result))

    def test_summary_and_markdown_make_provenance_explicit(self):
        result = discovery.inspect(CFG)
        text = discovery.summary(result)
        report = discovery.markdown(result)
        self.assertIn("configuration only", text)
        self.assertIn("Goal: Enable integration", text)
        self.assertIn("Purpose/responsibilities/boundaries: unknown", text)
        self.assertIn("No Jira, Confluence, SharePoint", report)
        self.assertIn("configured facts", report)

    def test_command_does_not_write_without_export(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("commands.discover.output.place") as place:
                with patch("builtins.print"):
                    discover.run(CFG, argparse.Namespace(
                        project=None, product=None, workstream=None,
                        export=False, out=folder))
                place.assert_not_called()
            self.assertEqual(os.listdir(folder), [])

    def test_explicit_export_writes_markdown(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("builtins.print"):
                discover.run(CFG, argparse.Namespace(
                    project="APS", product=None, workstream=None,
                    export=True, out=folder))
            with open(os.path.join(folder, "discovery.md"),
                      encoding="utf-8") as handle:
                report = handle.read()
            self.assertIn("Gateway", report)
            self.assertNotIn("#### Service (SVC)", report)


if __name__ == "__main__":
    unittest.main()
