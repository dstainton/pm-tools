"""Phase 1A whole-project inventory and Jira paging contracts."""

import unittest
from unittest.mock import patch

import requests

from core import inventory, sources


JIRA = {
    "base_url": "https://example.atlassian.net/",
    "email": "pm@example.com", "api_token": "token",
    "max_results": 100, "page_size": 60,
}
CFG = {"jira": JIRA}


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def issue(number, fields=None):
    return {"key": "APS-" + str(number), "fields": fields or {}}


class InventoryTests(unittest.TestCase):
    def test_all_pages_retrieved_beyond_default_cap_and_normalized(self):
        responses = [
            FakeResponse({"issues": [issue(i) for i in range(1, 61)],
                          "nextPageToken": "p2"}),
            FakeResponse({"issues": [issue(i) for i in range(61, 121)],
                          "nextPageToken": "p3"}),
            FakeResponse({"issues": [issue(i) for i in range(121, 132)]}),
        ]
        with patch("core.sources.requests.post", side_effect=responses) as post:
            result = inventory.open_issues(CFG, "APS")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["count"], 131)
        self.assertEqual(result["pages"], 3)
        self.assertEqual(result["issues"][0]["key"], "APS-1")
        self.assertEqual(result["issues"][-1]["key"], "APS-131")
        self.assertIn('project = "APS"', result["jql"])
        self.assertEqual(post.call_count, 3)
        self.assertNotIn("nextPageToken", post.call_args_list[0].kwargs["json"])
        self.assertEqual(post.call_args_list[1].kwargs["json"]["nextPageToken"], "p2")
        self.assertEqual(post.call_args_list[2].kwargs["json"]["nextPageToken"], "p3")
        for call in post.call_args_list:
            self.assertLessEqual(call.kwargs["json"]["maxResults"], 100)
        self.assertEqual(result["issues"][0]["components"], [])
        self.assertEqual(result["issues"][0]["labels"], [])
        self.assertIsNone(result["issues"][0]["story_points"])
        self.assertIn("story_points_field", result["missing_config"])

    def test_clean_empty_project_is_complete(self):
        with patch("core.sources.requests.post", return_value=FakeResponse({"issues": []})):
            result = inventory.open_issues(CFG, "APS")
        self.assertEqual((result["status"], result["count"], result["pages"]),
                         ("complete", 0, 1))

    def test_empty_project_argument_fails_without_query(self):
        with patch("core.sources.requests.post") as post:
            result = inventory.open_issues(CFG, "")
        self.assertEqual(result["status"], "failed")
        post.assert_not_called()

    def test_early_empty_page_with_continuation_is_partial(self):
        responses = [
            FakeResponse({"issues": [issue(1)], "nextPageToken": "p2"}),
            FakeResponse({"issues": [], "nextPageToken": "p3"}),
        ]
        with patch("core.sources.requests.post", side_effect=responses):
            result = inventory.open_issues(CFG, "APS")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["count"], 1)
        self.assertIn("empty page", result["reason"])

    def test_repeated_token_is_partial_not_an_infinite_loop(self):
        responses = [
            FakeResponse({"issues": [issue(1)], "nextPageToken": "p2"}),
            FakeResponse({"issues": [issue(2)], "nextPageToken": "p2"}),
        ]
        with patch("core.sources.requests.post", side_effect=responses) as post:
            result = inventory.open_issues(CFG, "APS")
        self.assertEqual(result["status"], "partial")
        self.assertIn("repeated", result["reason"])
        self.assertEqual(post.call_count, 2)

    def test_network_failure_after_one_page_preserves_partial_count(self):
        responses = [FakeResponse({"issues": [issue(1)], "nextPageToken": "p2"}),
                     requests.ConnectionError("network down")]
        with patch("core.sources.requests.post", side_effect=responses):
            result = inventory.open_issues(CFG, "APS")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["count"], 1)
        self.assertIn("ConnectionError", result["reason"])

    def test_first_page_api_error_is_failure_not_empty_project(self):
        with patch("core.sources.requests.post",
                   side_effect=requests.HTTPError("403 forbidden")):
            result = inventory.open_issues(CFG, "APS")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["pages"], 0)
        self.assertIn("403", result["reason"])

    def test_duplicate_and_malformed_issues_do_not_inflate_counts(self):
        responses = [FakeResponse({"issues": [issue(1), issue(2), issue(1),
                                               {"fields": {}}]})]
        with patch("core.sources.requests.post", side_effect=responses):
            result = inventory.open_issues(CFG, "APS")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["count"], 2)
        self.assertIn("1 duplicate keys; 1 malformed", result["reason"])

    def test_invalid_jira_payload_is_not_reported_as_empty(self):
        with patch("core.sources.requests.post",
                   return_value=FakeResponse({"unexpected": []})):
            result = inventory.open_issues(CFG, "APS")
        self.assertEqual(result["status"], "failed")
        self.assertIn("ValueError", result["reason"])

    def test_existing_list_api_still_has_configured_limit(self):
        responses = [
            FakeResponse({"issues": [issue(i) for i in range(100)],
                          "nextPageToken": "p2"}),
        ]
        with patch("core.sources.requests.post", side_effect=responses):
            rows = sources.search_issues(JIRA, "project = APS")
        self.assertEqual(len(rows), 100)

    def test_missing_optional_fields_are_reported_separately_from_zero(self):
        jira = dict(JIRA, story_points_field="customfield_10303")
        cfg = {"jira": jira}
        with patch("core.sources.requests.post", return_value=FakeResponse(
                {"issues": [issue(1, {"customfield_10303": 0}),
                            issue(2)]})):
            result = inventory.open_issues(cfg, "APS")
        self.assertNotIn("story_points_field", result["missing_config"])
        self.assertEqual(result["issues"][0]["story_points"], 0)
        self.assertIsNone(result["issues"][1]["story_points"])


if __name__ == "__main__":
    unittest.main()
