"""All-status project-wide Jira inventory baseline."""
import unittest
from unittest.mock import patch

from core import discovery_jira_inventory


class JiraInventoryTests(unittest.TestCase):
    def test_includes_closed_and_custom_hierarchy(self):
        cfg = {"jira": {"base_url": "https://jira.example"}}
        issues = [
            {"key": "APS-1", "fields": {"issuetype": {"name": "Initiative",
                  "hierarchyLevel": 2}, "status": {"name": "Closed"},
                  "labels": ["old"], "components": [{"name": "P2P"}]}},
            {"key": "APS-2", "fields": {"issuetype": {"name": "Sub-task",
                  "hierarchyLevel": -1}, "parent": {"key": "APS-1"},
                  "status": {"name": "Done"}}},
        ]
        with patch("core.discovery_jira_inventory.sources.search_issues",
                   return_value={"issues": issues, "complete": True}) as fetch:
            report = discovery_jira_inventory.build(cfg, ["APS"])
        self.assertEqual(report["coverage"], "complete")
        self.assertEqual(len(report["issues"]), 2)
        self.assertEqual(report["issues"][0]["status"], "Closed")
        self.assertEqual(report["issues"][0]["hierarchy_level"], 2)
        self.assertEqual(report["issues"][1]["parent_key"], "APS-1")
        kwargs = fetch.call_args.kwargs
        self.assertEqual(kwargs["max_items"], 0)
        self.assertEqual(kwargs["with_metadata"], True)
        self.assertNotIn("status", fetch.call_args.args[1].lower().split("order")[0])

    def test_incomplete_crawl_is_not_complete(self):
        with patch("core.discovery_jira_inventory.sources.search_issues",
                   return_value={"issues": [], "complete": False,
                                 "reason": "continuation repeated"}):
            report = discovery_jira_inventory.build({"jira": {}}, ["APS"])
        self.assertEqual(report["coverage"], "partial")
        self.assertEqual(report["projects"][0]["status"], "incomplete")

    def test_no_projects_does_not_query(self):
        with patch("core.discovery_jira_inventory.sources.search_issues") as fetch:
            report = discovery_jira_inventory.build({"jira": {}}, [])
        self.assertEqual(report["coverage"], "unconfigured")
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
