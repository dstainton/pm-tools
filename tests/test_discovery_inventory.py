"""Inventory coverage must not imply complete retrieval after caps or errors."""
import unittest
from unittest.mock import patch

from core import discovery_inventory


CFG = {"confluence": {"base_url": "https://wiki.example", "space": "TEAM"},
       "products": [], "workstreams": []}


def page(n):
    return {"id": str(n), "title": "Page " + str(n),
            "type": "page", "version": {"when": "2026-01-02"},
            "ancestors": [{"id": "10"}]}


class InventoryTests(unittest.TestCase):
    def test_complete_two_pages(self):
        with patch("core.discovery_inventory.sources.list_confluence_inventory",
                   side_effect=[([page(1), page(2)], False)]) as fetch:
            report = discovery_inventory.build(CFG, {}, cap=30)
        self.assertEqual(report["inventory"]["coverage"], "complete")
        self.assertEqual(report["inventory"]["scopes"][0]["retrieved"], 2)
        self.assertEqual(report["inventory"]["pages"][0]["ancestors"], ["10"])
        fetch.assert_called_once_with(CFG, "TEAM", start=0, limit=25)

    def test_cap_does_not_claim_complete(self):
        with patch("core.discovery_inventory.sources.list_confluence_inventory",
                   return_value=([page(1), page(2)], True)):
            report = discovery_inventory.build(CFG, {}, cap=2)
        self.assertEqual(report["inventory"]["coverage"], "partial")
        self.assertEqual(report["inventory"]["scopes"][0]["status"], "truncated")

    def test_partial_failure_retains_retrieved_pages(self):
        with patch("core.discovery_inventory.sources.list_confluence_inventory",
                   side_effect=[([page(n) for n in range(25)], True),
                                PermissionError("forbidden")]):
            report = discovery_inventory.build(CFG, {}, cap=50)
        self.assertEqual(report["inventory"]["scopes"][0]["status"], "incomplete")
        self.assertEqual(report["inventory"]["scopes"][0]["retrieved"], 25)

    def test_no_space_no_requests(self):
        with patch("core.discovery_inventory.sources.list_confluence_inventory") as fetch:
            report = discovery_inventory.build({}, {})
        fetch.assert_not_called()
        self.assertEqual(report["inventory"]["coverage"], "unconfigured")


    def test_aps_tree_excludes_posm_sibling_teams(self):
        cfg = {"confluence": {"base_url": "https://wiki.example",
                              "space": "POSM", "team_page_id": "42"},
               "products": [], "workstreams": []}
        root = {"id": "42", "title": "APS", "space": {"key": "POSM"},
                "ancestors": [], "version": {"when": "2026-01-01"}}
        aps = {"id": "43", "title": "Gateway", "ancestors": [{"id": "42"}]}
        loc = {"id": "44", "title": "LOC", "ancestors": [{"id": "10"}]}
        with patch("core.discovery_inventory.sources.fetch_confluence_page",
                   return_value=root), patch(
                       "core.discovery_inventory.sources.list_confluence_inventory",
                       return_value=([aps, loc], False)) as fetch:
            report = discovery_inventory.build(cfg, {})
        self.assertEqual([p["id"] for p in report["inventory"]["pages"]],
                         ["42", "43"])
        fetch.assert_called_once_with(cfg, "POSM", start=0, limit=25,
                                      ancestor_id="42")

    def test_explicit_space_scope(self):
        cfg = {"confluence": {"base_url": "https://wiki.example",
                              "space": "POSM",
                              "scopes": [{"type": "space", "space_key": "POSM"}]}}
        with patch("core.discovery_inventory.sources.list_confluence_inventory",
                   return_value=([page(1)], False)) as fetch:
            report = discovery_inventory.build(cfg, {})
        self.assertEqual(report["inventory"]["coverage"], "complete")
        fetch.assert_called_once_with(cfg, "POSM", start=0, limit=25)

    def test_duplicate_only_page_is_incomplete(self):
        with patch("core.discovery_inventory.sources.list_confluence_inventory",
                   return_value=([page(1)], True)):
            report = discovery_inventory.build(CFG, {})
        self.assertEqual(report["inventory"]["scopes"][0]["status"],
                         "incomplete")

    def test_missing_tree_root_never_falls_back_to_space(self):
        cfg = {"confluence": {"base_url": "https://wiki.example",
                              "space": "POSM", "root_page_id": 42}}
        with patch("core.discovery_inventory.sources.fetch_confluence_page",
                   return_value=None), patch(
                       "core.discovery_inventory.sources.list_confluence_inventory") as fetch:
            report = discovery_inventory.build(cfg, {})
        self.assertEqual(report["inventory"]["scopes"][0]["status"], "unavailable")
        fetch.assert_not_called()

    def test_page_scopes_are_not_widened_by_default_space(self):
        cfg = {"confluence": {"base_url": "https://wiki.example", "space": "POSM"},
               "products": [{"confluence_page_id": 42}], "workstreams": []}
        scopes = discovery_inventory._scopes(cfg)
        self.assertEqual(len(scopes), 1)
        self.assertEqual(scopes[0]["type"], "page_tree")


if __name__ == "__main__":
    unittest.main()
