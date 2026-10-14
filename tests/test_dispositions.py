"""Deterministic portable Jira disposition classification tests."""
import unittest
from unittest.mock import patch

from core import dispositions


STATUSES = [
    {"id": "1", "name": "To Do", "category": "new"},
    {"id": "2", "name": "In Progress", "category": "indeterminate"},
    {"id": "3", "name": "Done", "category": "done"},
    {"id": "4", "name": "Cancelled", "category": "new"},
    {"id": "5", "name": "Won't Do", "category": "done"},
    {"id": "6", "name": "QA Accepted", "category": "indeterminate"},
]


class DispositionTests(unittest.TestCase):
    def setUp(self):
        self.status_patch = patch("core.dispositions.sources.fetch_project_statuses",
                                  return_value=STATUSES)
        self.status_patch.start()
        self.addCleanup(self.status_patch.stop)
        self.cfg = {"jira": {"project": "APS"}}

    def test_defaults_use_project_statuses_not_unavailable_aliases(self):
        result = dispositions.resolve(self.cfg, "APS")
        self.assertEqual(result["status_names"]["excluded"], ["Cancelled", "Won't Do"])
        self.assertEqual(result["status_names"]["completed"], ["Done"])
        self.assertEqual(result["status_names"]["active"],
                         ["In Progress", "QA Accepted", "To Do"])
        self.assertIn("status IN (1, 2, 6)", result["jql"]["active"])
        self.assertIn("status IN (4, 5)", result["jql"]["excluded"])

    def test_explicit_project_override_takes_precedence(self):
        self.cfg["assessment"] = {"dispositions": {
            "active": ["Done"],
            "projects": {"APS": {"excluded": ["QA Accepted"]}}}}
        result = dispositions.resolve(self.cfg, "APS")
        self.assertEqual(result["status_names"]["excluded"], ["QA Accepted"])
        self.assertIn("Done", result["status_names"]["active"])
        self.assertIn("Cancelled", result["status_names"]["active"])

    def test_explicit_completed_can_override_non_done_category(self):
        self.cfg["assessment"] = {"dispositions": {"completed": ["QA Accepted"]}}
        result = dispositions.resolve(self.cfg, "APS")
        self.assertIn("QA Accepted", result["status_names"]["completed"])

    def test_invalid_config_name_fails_before_search(self):
        self.cfg["assessment"] = {"dispositions": {"excluded": ["Typo State"]}}
        with self.assertRaisesRegex(ValueError, "Unknown excluded"):
            dispositions.resolve(self.cfg, "APS")

    def test_unknown_status_category_fails_closed(self):
        with patch("core.dispositions.sources.fetch_project_statuses",
                   return_value=[{"id": "10", "name": "Mystery",
                                  "category": "unknown"}]):
            with self.assertRaisesRegex(ValueError, "Unknown Jira status category"):
                dispositions.resolve(self.cfg, "APS")

    def test_empty_population_generates_impossible_query(self):
        with patch("core.dispositions.sources.fetch_project_statuses",
                   return_value=[{"id": "1", "name": "Done", "category": "done"}]):
            result = dispositions.resolve(self.cfg, "APS")
            self.assertIn("statusCategory = Done AND statusCategory != Done",
                          result["jql"]["excluded"])


if __name__ == "__main__":
    unittest.main()
