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


class JiraKeyPagingTests(unittest.TestCase):
    def test_fetch_jira_keys_pages_until_total(self):
        responses = [
            FakeResponse({"total": 3, "issues": [{"key": "APS-1"}, {"key": "APS-2"}]}),
            FakeResponse({"total": 3, "issues": [{"key": "APS-3"}]}),
        ]
        cfg = {
            "base_url": "https://example.atlassian.net",
            "email": "pm@example.com",
            "api_token": "token",
            "max_results": 2,
        }
        with patch("core.sources.requests.get", side_effect=responses) as get:
            keys = sources.fetch_jira_keys(cfg, 'project = "APS"')

        self.assertEqual(keys, ["APS-1", "APS-2", "APS-3"])
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args_list[1].kwargs["params"]["startAt"], 2)


if __name__ == "__main__":
    unittest.main()
