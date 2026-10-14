"""Phase 1D deterministic investigation queue tests."""

import unittest

from core import review_queue
from commands import assess


def issue(key, summary="Example", status="new"):
    return {"key": key, "summary": summary,
            "status": "To Do", "status_category": status,
            "url": "https://jira.example/browse/" + key}


def finding(key, rule, days=20):
    return {"key": key, "rule": rule, "url": "https://jira.example/browse/" + key,
            "detail": "Review required", "updated_age_days": days}


class ReviewQueueTests(unittest.TestCase):
    def test_stalled_unassigned_precedes_other_groups_without_duplication(self):
        rows = [issue("APS-1", "Active without owner", "indeterminate"),
                issue("APS-2", "Old inherited ticket"),
                issue("APS-3", "Current overdue work"),
                issue("APS-4", "Ordinary missing field")]
        findings = [finding("APS-1", "stalled-active", 40),
                    finding("APS-1", "unassigned-person", 40),
                    finding("APS-1", "unclaimed-workstream", 40),
                    finding("APS-2", "unclaimed-workstream", 500),
                    finding("APS-3", "overdue", 5),
                    finding("APS-4", "missing-labels", 3)]
        groups = review_queue.build({"issues": rows}, {"findings": findings})
        self.assertEqual([g["id"] for g in groups],
                         ["stalled-unassigned", "overdue", "unclaimed-old", "other"])
        self.assertEqual(sum(g["count"] for g in groups), 4)
        self.assertEqual(groups[0]["sample"][0]["key"], "APS-1")

    def test_sort_and_sample_limit_do_not_change_true_count(self):
        rows = [issue("APS-{}".format(i)) for i in range(1, 5)]
        flags = [finding("APS-{}".format(i), "missing-component", i * 10)
                 for i in range(1, 5)]
        groups = review_queue.build({"issues": rows}, {"findings": flags},
                                    sample_limit=2)
        self.assertEqual(groups[0]["count"], 4)
        self.assertEqual(len(groups[0]["sample"]), 2)
        self.assertEqual(groups[0]["sample"][0]["key"], "APS-4")

    def test_no_findings_produces_empty_queue(self):
        self.assertEqual(review_queue.build(
            {"issues": [issue("APS-1")]}, {"findings": []}), [])

    def test_markdown_keeps_complete_rule_evidence(self):
        row = issue("APS-9", "Needs | review")
        inv = {"project": "APS", "jql": "project = APS",
               "retrieved_at": "2026-10-14T16:00:00Z",
               "pages": 1, "missing_config": [], "issues": [row]}
        fact = {"project": "APS", "today": "2026-10-14",
                "inventory_status": "complete", "inventory_reason": "",
                "complete": True, "count": 1, "ownership_evaluated": False,
                "by_type": {"Task": 1}, "by_status_category": {"new": 1},
                "created_age_bands": {"0-30": 1},
                "updated_age_bands": {"0-30": 1},
                "finding_counts": {"missing-labels": 1},
                "findings": [finding("APS-9", "missing-labels")]}
        output = assess.markdown([(inv, fact)])
        self.assertIn("### Investigation queue", output)
        self.assertIn("Needs \\| review", output)
        self.assertIn("### Complete rule evidence (appendix)", output)
        self.assertIn("| missing-labels | [APS-9]", output)


if __name__ == "__main__":
    unittest.main()
