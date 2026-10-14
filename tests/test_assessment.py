"""Pure Phase 1B assessment tests with frozen clock and synthetic issues."""

import datetime as dt
import unittest

from core import assessment


TODAY = dt.date(2026, 10, 14)


def issue(key, **changes):
    base = {
        "key": key, "url": "https://jira.example/browse/" + key,
        "issuetype": "Story", "status_category": "new",
        "created": "2026-01-01", "updated": "2026-10-01",
        "components": [], "labels": [], "description": "",
        "assignee": "Unassigned", "epic": None, "story_points": None,
        "acceptance_criteria": "", "due_date": None,
    }
    base.update(changes)
    return base


def inventory(rows, status="complete"):
    return {"project": "APS", "status": status, "issues": rows,
            "reason": "pagination stopped" if status != "complete" else ""}


class AssessmentTests(unittest.TestCase):
    def test_empty_complete_inventory_has_no_findings(self):
        result = assessment.analyze(inventory([]), TODAY)
        self.assertTrue(result["complete"])
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["finding_counts"], {})
        self.assertFalse(result["ownership_evaluated"])

    def test_partial_inventory_never_claims_completeness(self):
        result = assessment.analyze(inventory([issue("APS-1")], "partial"), TODAY)
        self.assertFalse(result["complete"])
        self.assertEqual(result["inventory_reason"], "pagination stopped")
        self.assertEqual(result["count"], 1)

    def test_missing_metadata_retained_with_unknown_age(self):
        result = assessment.analyze(inventory([
            issue("APS-1", created=None, updated=None),
        ]), TODAY)
        self.assertEqual(result["created_age_bands"]["unknown"], 1)
        self.assertEqual(result["updated_age_bands"]["unknown"], 1)
        self.assertEqual(result["finding_counts"]["missing-component"], 1)
        self.assertEqual(result["finding_counts"]["missing-labels"], 1)
        self.assertEqual(result["finding_counts"]["missing-estimate"], 1)
        self.assertEqual(result["finding_counts"]["missing-parent"], 1)
        self.assertNotIn("unclaimed-workstream", result["finding_counts"])

    def test_distinguish_zero_estimate_from_missing_estimate(self):
        result = assessment.analyze(inventory([
            issue("APS-1", story_points=0),
            issue("APS-2", story_points=None),
        ]), TODAY)
        self.assertEqual(result["finding_counts"]["missing-estimate"], 1)

    def test_workstream_claims_are_distinct_from_components(self):
        rows = [issue("APS-1", components=["Gateway"]),
                issue("APS-2", components=["Gateway"]),
                issue("APS-3", components=["Gateway"])]
        result = assessment.analyze(inventory(rows), TODAY, claims={
            "APS-1": ["SDX"],
            "APS-2": ["SDX", "ITK", "SDX"],
        })
        self.assertTrue(result["ownership_evaluated"])
        self.assertEqual(result["finding_counts"]["unclaimed-workstream"], 1)
        self.assertEqual(result["finding_counts"]["multiple-workstreams"], 1)
        self.assertNotIn("missing-component", result["finding_counts"])

    def test_epics_do_not_require_parent_or_story_estimate(self):
        result = assessment.analyze(inventory([
            issue("APS-1", issuetype="Epic", story_points=None),
        ]), TODAY)
        self.assertNotIn("missing-parent", result["finding_counts"])
        self.assertNotIn("missing-estimate", result["finding_counts"])

    def test_aging_bands_and_statuses_are_deterministic(self):
        result = assessment.analyze(inventory([
            issue("APS-1", created="2026-10-14", updated="2026-10-14",
                  status_category="indeterminate"),
            issue("APS-2", created="2026-07-01", updated="2026-01-01"),
        ]), TODAY)
        self.assertEqual(result["created_age_bands"]["0-30"], 1)
        self.assertEqual(result["created_age_bands"]["91-180"], 1)
        self.assertEqual(result["updated_age_bands"]["181-365"], 1)
        self.assertEqual(result["by_status_category"]["indeterminate"], 1)
        self.assertEqual(result["by_status_category"]["new"], 1)

    def test_stalled_and_overdue_are_review_signals(self):
        result = assessment.analyze(inventory([
            issue("APS-1", status_category="indeterminate",
                  updated="2026-08-01", due_date="2026-09-30"),
        ]), TODAY)
        self.assertEqual(result["finding_counts"]["stalled-active"], 1)
        self.assertEqual(result["finding_counts"]["overdue"], 1)

    def test_stale_unstarted_issue_does_not_get_stalled_active_flag(self):
        result = assessment.analyze(inventory([
            issue("APS-1", updated="2025-01-01", status_category="new"),
        ]), TODAY)
        self.assertNotIn("stalled-active", result["finding_counts"])

    def test_invalid_or_missing_dates_do_not_crash(self):
        result = assessment.analyze(inventory([
            issue("APS-1", created="garbage", updated=None, due_date="not a date"),
        ]), TODAY)
        self.assertEqual(result["created_age_bands"]["unknown"], 1)

    def test_result_is_input_order_independent_for_findings(self):
        rows = [issue("APS-2"), issue("APS-1")]
        x = assessment.analyze(inventory(rows), TODAY)
        y = assessment.analyze(inventory(list(reversed(rows))), TODAY)
        self.assertEqual(x["findings"], y["findings"])
        self.assertEqual(x["finding_counts"], y["finding_counts"])

    def test_bad_clock_is_rejected(self):
        with self.assertRaises(ValueError):
            assessment.analyze(inventory([]), "wrong")


if __name__ == "__main__":
    unittest.main()
