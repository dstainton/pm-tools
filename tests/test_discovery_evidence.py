"""Phase 2B evidence retrieval is bounded, sourced, optional and read-only."""
import argparse
import unittest
from unittest.mock import patch

from commands import discover
from core import discovery, discovery_evidence

CFG = {
    "jira": {"base_url": "https://example.atlassian.net", "project": "ONE"},
    "confluence": {"base_url": "https://wiki.example", "email": "a", "api_token": "b"},
    "products": [{"name": "Product", "abbrev": "P", "project": "ONE",
                  "confluence_page_id": "88"}],
    "workstreams": [{"name": "Gateway", "abbrev": "GW", "product": "P",
                     "components": ["Gateway"], "confluence_page_id": "99"}],
}


class EvidenceTests(unittest.TestCase):
    def test_title_reference_in_workstream_configuration_is_resolved(self):
        cfg = dict(CFG)
        cfg["workstreams"] = [dict(CFG["workstreams"][0],
                                   confluence_page_id=None,
                                   confluence_space="TEAM",
                                   confluence_page="Gateway Overview")]
        payload = {"id": "912", "title": "Gateway Overview",
                   "version": {"when": "2026-10-01"}}
        with patch("core.discovery_evidence.sources.search_confluence_by_title",
                   return_value=[payload]) as lookup:
            evidence = discovery_evidence._page(cfg, cfg["workstreams"][0])
        lookup.assert_called_once_with(cfg, "TEAM", "Gateway Overview")
        self.assertEqual(evidence["state"], "retrieved")
        self.assertEqual(evidence["reference"], "912")

    def test_title_reference_can_inherit_global_space(self):
        cfg = dict(CFG, confluence=dict(CFG["confluence"], space="TEAM"))
        entity = {"confluence_page": "Gateway Overview"}
        with patch("core.discovery_evidence.sources.search_confluence_by_title",
                   return_value=[{"id": "2", "title": "Gateway Overview"}]) as lookup:
            evidence = discovery_evidence._page(cfg, entity)
        lookup.assert_called_once_with(cfg, "TEAM", "Gateway Overview")
        self.assertEqual(evidence["state"], "retrieved")

    def test_duplicate_titles_require_explicit_page_id(self):
        entity = {"confluence_space": "TEAM", "confluence_page": "Overview"}
        with patch("core.discovery_evidence.sources.search_confluence_by_title",
                   return_value=[{"id": "1"}, {"id": "2"}]):
            evidence = discovery_evidence._page(CFG, entity)
        self.assertEqual(evidence["state"], "ambiguous")
        self.assertIn("confluence_page_id", evidence["detail"])

    def test_space_only_is_configured_but_not_a_page_reference(self):
        with patch("core.discovery_evidence.sources.search_confluence_by_title") as lookup:
            evidence = discovery_evidence._page(CFG, {"confluence_space": "TEAM"})
        lookup.assert_not_called()
        self.assertEqual(evidence["state"], "configured")

    def test_terminal_coverage_reflects_source_enrichment(self):
        report = discovery.inspect(CFG)
        with patch("core.discovery_evidence.sources.fetch_confluence_page",
                   return_value=None), patch(
                   "core.discovery_evidence.sources.search_issues",
                   return_value=[]):
            discovery_evidence.enrich(CFG, report)
        self.assertIn("bounded Jira Epic samples", discovery.summary(report))
        self.assertNotIn("configuration only (no Jira", discovery.summary(report))

    def test_bounded_evidence_never_confirmed_as_responsibility(self):
        payload = {"id": "88", "title": "Product strategy",
                   "version": {"when": "2026-09-01"},
                   "body": {"storage": {"value": "<p>Product scope is emerging.</p>"}}}
        rows = [{"key": "ONE-1", "fields": {"summary": "Gateway work",
                                                 "updated": "2026-10-01"}}]
        with patch("core.discovery_evidence.sources.fetch_confluence_page",
                   return_value=payload) as page, patch(
                   "core.discovery_evidence.sources.search_issues",
                   return_value=rows) as jira:
            result = discovery_evidence.enrich(CFG, discovery.inspect(CFG))
        self.assertEqual(page.call_count, 2)
        self.assertEqual(jira.call_count, 1)
        self.assertEqual(jira.call_args.kwargs["max_items"], 8)
        self.assertEqual(result["workstreams"][0]["evidence"][1]["items"][0]["key"], "ONE-1")
        rendered = discovery.markdown(result)
        self.assertIn("ONE-1", rendered)
        self.assertIn("Product strategy", rendered)
        self.assertIn("Purpose: unknown", rendered)
        self.assertIn("not exhaustive", rendered)

    def test_unavailable_sources_preserve_unknowns(self):
        with patch("core.discovery_evidence.sources.fetch_confluence_page",
                   side_effect=PermissionError("access denied")), patch(
                   "core.discovery_evidence.sources.search_issues",
                   side_effect=RuntimeError("Jira down")):
            result = discovery_evidence.enrich(CFG, discovery.inspect(CFG))
        self.assertIn("unavailable", discovery.summary(result))
        self.assertIn("Responsibilities: unknown", discovery.markdown(result))

    def test_no_source_configuration_makes_no_requests(self):
        cfg = {"jira": {"project": "ONE"}, "workstreams": [{
            "name": "No anchor", "abbrev": "X", "jira_jql": "project = ONE"}]}
        with patch("core.discovery_evidence.sources.fetch_confluence_page") as page, patch(
                "core.discovery_evidence.sources.search_issues") as jira:
            result = discovery_evidence.enrich(cfg, discovery.inspect(cfg))
        page.assert_not_called()
        jira.assert_not_called()
        self.assertIn("not configured", discovery.summary(result))

    def test_command_does_not_enrich_without_opt_in(self):
        args = argparse.Namespace(project=None, product=None, workstream=None,
                                  export=False, enrich=False, out=None)
        with patch("core.discovery_evidence.enrich") as enrich, patch("builtins.print"):
            discover.run(CFG, args)
        enrich.assert_not_called()


if __name__ == "__main__":
    unittest.main()
