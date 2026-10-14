"""Regression tests for story-point summaries in weekly reports."""

import unittest
from core import report_render, sources


def issue(key, points, status="indeterminate", issuetype="Story"):
    return {"source": "Jira", "key": key, "issuetype": issuetype,
            "story_points": points, "status_category": status}


class StoryPointReportTests(unittest.TestCase):
    def test_report_fields_include_configured_story_point_field(self):
        fields = sources._report_fields({
            "fields": "summary,status",
            "story_points_field": "customfield_10303",
        })
        self.assertIn("customfield_10303", fields)
        self.assertIn("parent", fields)

    def test_totals_distinguish_missing_and_zero_estimates(self):
        items = [
            issue("APS-1", 5, "done"),
            issue("APS-2", 3),
            issue("APS-3", 0),
            issue("APS-4", None),
            issue("APS-5", None, issuetype="Epic"),
        ]
        totals = report_render._story_point_totals([{"items": items}])
        self.assertEqual(totals, {"done": 5, "open": 3,
                                  "unestimated": 1, "issues": 4})

    def test_duplicate_issues_are_not_counted_twice(self):
        same = issue("APS-6", 8)
        totals = report_render._story_point_totals([
            {"items": [same]}, {"items": [same]}
        ])
        self.assertEqual(totals["open"], 8)
        self.assertEqual(totals["issues"], 1)

    def test_summary_is_not_presented_as_weekly_velocity(self):
        line = report_render._story_points_line([
            {"items": [issue("APS-7", 2, "done")]}
        ])
        self.assertIn("2 Done", line)
        self.assertIn("not points completed this week", line)


if __name__ == "__main__":
    unittest.main()
