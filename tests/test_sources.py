import unittest
from unittest.mock import patch

from core import sources


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


CFG = {
    "base_url": "https://example.atlassian.net/",
    "email": "pm@example.com",
    "api_token": "token",
    "max_results": 100,
    "page_size": 2,
}


class SearchTests(unittest.TestCase):
    def test_paging_follows_next_page_token(self):
        responses = [
            FakeResponse({"nextPageToken": "t1",
                          "issues": [{"key": "APS-1"}, {"key": "APS-2"}]}),
            FakeResponse({"issues": [{"key": "APS-3"}]}),
        ]
        with patch("core.sources.requests.post", side_effect=responses) as post:
            keys = sources.fetch_jira_keys(CFG, 'project = "APS"')

        self.assertEqual(keys, ["APS-1", "APS-2", "APS-3"])
        self.assertEqual(post.call_count, 2)
        first, second = post.call_args_list
        self.assertEqual(first.args[0],
                         "https://example.atlassian.net/rest/api/3/search/jql")
        self.assertEqual(first.kwargs["json"]["fields"], ["key"])
        self.assertNotIn("nextPageToken", first.kwargs["json"])
        self.assertEqual(second.kwargs["json"]["nextPageToken"], "t1")

    def test_item_cap_stops_paging(self):
        responses = [
            FakeResponse({"nextPageToken": "t1",
                          "issues": [{"key": "APS-1"}, {"key": "APS-2"}]}),
            FakeResponse({"nextPageToken": "t2",
                          "issues": [{"key": "APS-3"}, {"key": "APS-4"}]}),
        ]
        with patch("core.sources.requests.post", side_effect=responses) as post:
            issues = sources.search_issues(CFG, "project = APS", max_items=3)

        self.assertEqual([i["key"] for i in issues],
                         ["APS-1", "APS-2", "APS-3"])
        self.assertEqual(post.call_count, 2)

    def test_fields_string_is_sent_as_a_list(self):
        with patch("core.sources.requests.post",
                   return_value=FakeResponse({"issues": []})) as post:
            sources.search_issues(CFG, "project = APS", fields="summary,status")
        self.assertEqual(post.call_args.kwargs["json"]["fields"],
                         ["summary", "status"])

    def test_empty_jql_never_calls_jira(self):
        with patch("core.sources.requests.post") as post:
            self.assertEqual(sources.search_issues(CFG, None), [])
            self.assertEqual(sources.fetch_jira_keys(CFG, ""), [])
        post.assert_not_called()

    def test_approximate_count(self):
        with patch("core.sources.requests.post",
                   return_value=FakeResponse({"count": 42})) as post:
            self.assertEqual(sources.approximate_count(CFG, "project = APS"), 42)
        self.assertTrue(post.call_args.args[0].endswith(
            "/rest/api/3/search/approximate-count"))


class ChangelogTests(unittest.TestCase):
    ISSUE = {
        "key": "APS-5",
        "fields": {"summary": "Move the thing",
                   "status": {"name": "In Review"},
                   "assignee": {"displayName": "A. Lee"},
                   "issuetype": {"name": "Story"}},
    }

    def test_transitions_come_from_the_expanded_changelog(self):
        issue = dict(self.ISSUE)
        issue["changelog"] = {"histories": [
            {"created": "2999-01-01T09:12:00.000+0000",
             "author": {"displayName": "A. Lee"},
             "items": [{"field": "status", "fromString": "To Do",
                        "toString": "In Review"}]},
        ]}
        with patch("core.sources.search_issues", return_value=[issue]):
            moved = sources.fetch_jira_changelog(CFG, "project = APS", 1)

        self.assertEqual(len(moved), 1)
        self.assertEqual(moved[0]["transitions"][0]["from"], "To Do")
        self.assertEqual(moved[0]["transitions"][0]["to"], "In Review")

    def test_missing_changelog_falls_back_to_the_issue_endpoint(self):
        histories = [{"created": "2999-01-01T09:12:00.000+0000",
                      "author": {"displayName": "A. Lee"},
                      "items": [{"field": "status", "fromString": "To Do",
                                 "toString": "Done"}]}]
        with patch("core.sources.search_issues", return_value=[dict(self.ISSUE)]), \
                patch("core.sources.fetch_issue_changelog",
                      return_value=histories) as per_issue:
            moved = sources.fetch_jira_changelog(CFG, "project = APS", 1)

        per_issue.assert_called_once()
        self.assertEqual(moved[0]["transitions"][0]["to"], "Done")

    def test_issues_without_recent_movement_are_dropped(self):
        issue = dict(self.ISSUE)
        issue["changelog"] = {"histories": [
            {"created": "2000-01-01T09:12:00.000+0000",
             "items": [{"field": "status", "fromString": "To Do",
                        "toString": "Done"}]},
        ]}
        with patch("core.sources.search_issues", return_value=[issue]):
            self.assertEqual(
                sources.fetch_jira_changelog(CFG, "project = APS", 1), [])


if __name__ == "__main__":
    unittest.main()
