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


if __name__ == "__main__":
    unittest.main()
