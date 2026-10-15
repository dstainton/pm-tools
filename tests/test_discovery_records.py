"""Phase 2C evidence records must not infer ownership from source fields."""
import unittest

from core.discovery_records import confluence_page, jira_issue


class EvidenceContractTests(unittest.TestCase):
    def test_closed_issue_and_custom_hierarchy_are_preserved(self):
        item = {"id": "1001", "key": "EX-12", "fields": {
            "project": {"key": "EX"}, "issuetype": {
                "id": "10040", "name": "Strategic Initiative", "hierarchyLevel": 2},
            "status": {"name": "Closed", "statusCategory": {"key": "done"}},
            "parent": {"key": "EX-3"}, "labels": ["legacy-name"],
            "components": [{"id": "7", "name": "Subsystem"}],
            "created": "2024-01-01", "updated": "2026-01-01",
            "resolutiondate": "2025-01-01", "summary": "Retire prior naming"}}
        row = jira_issue(item)
        self.assertEqual(row["hierarchy_level"], 2)
        self.assertEqual(row["issue_type"], "Strategic Initiative")
        self.assertEqual(row["status"], "Closed")
        self.assertEqual(row["parent_key"], "EX-3")
        self.assertEqual(row["labels_direct"], ["legacy-name"])
        self.assertFalse(row["ownership_confirmed"])

    def test_subtask_is_not_assigned_parent_component(self):
        item = {"key": "EX-15", "fields": {
            "parent": {"key": "EX-12", "fields": {
                "components": [{"name": "Parent Product"}]}},
            "issuetype": {"name": "Sub-task", "hierarchyLevel": -1}}}
        row = jira_issue(item)
        self.assertEqual(row["components_direct"], [])
        self.assertEqual(row["labels_direct"], [])
        self.assertEqual(row["hierarchy_level"], -1)

    def test_confluence_scope_is_not_ownership(self):
        page = {"id": "41", "title": "Architecture",
                "space": {"key": "SHARED"},
                "ancestors": [{"id": "12"}, {"id": "13"}],
                "version": {"when": "2026-01-01"}}
        row = confluence_page(page, scope_id="tree:13")
        self.assertEqual(row["ancestor_ids"], ["12", "13"])
        self.assertEqual(row["scope_id"], "tree:13")
        self.assertFalse(row["ownership_confirmed"])

    def test_missing_identity_rejected(self):
        with self.assertRaises(ValueError):
            jira_issue({"fields": {}})
        with self.assertRaises(ValueError):
            confluence_page({"title": "No ID"})


if __name__ == "__main__":
    unittest.main()
