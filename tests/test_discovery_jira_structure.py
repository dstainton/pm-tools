"""Jira project metadata is descriptive, never product ownership."""
import unittest
from unittest.mock import patch
from core import discovery_jira_structure


class Response:
    def raise_for_status(self):
        pass

    def json(self):
        return {"issueTypes": [
            {"id": "1", "name": "Initiative", "hierarchyLevel": 2},
            {"id": "2", "name": "Epic", "hierarchyLevel": 1},
            {"id": "3", "name": "Sub-task", "subtask": True, "hierarchyLevel": -1}],
            "components": [{"id": "40", "name": "API Gateway"}]}


class FieldResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return [{"id": "customfield_10012", "name": "Product Area",
                 "custom": True, "schema": {"type": "string"}}]


class StructureTests(unittest.TestCase):
    def test_custom_hierarchy_and_components(self):
        with patch("core.discovery_jira_structure.sources.send", side_effect=[Response(), FieldResponse()]):
            result = discovery_jira_structure.inspect(
                {"jira": {"base_url": "https://jira.example", "email": "x", "api_token": "t"}},
                ["APS"])
        self.assertEqual(result["coverage"], "complete")
        self.assertEqual(result["projects"][0]["issue_types"][0]["hierarchy_level"], 2)
        self.assertEqual(result["projects"][0]["components"][0]["name"], "API Gateway")
        self.assertNotIn("owner", result["projects"][0])
        self.assertIn("versions_coverage", result["projects"][0])
        self.assertEqual(result["projects"][0]["fields"][0]["id"], "customfield_10012")
        self.assertIn("unverified", result["projects"][0]["fields_coverage"])

    def test_denied_project_is_not_complete(self):
        with patch("core.discovery_jira_structure.sources.send",
                   side_effect=PermissionError("no access")):
            result = discovery_jira_structure.inspect(
                {"jira": {"base_url": "https://jira.example", "email": "x",
                          "api_token": "t"}}, ["APS"])
        self.assertEqual(result["coverage"], "partial")
        self.assertEqual(result["projects"][0]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
