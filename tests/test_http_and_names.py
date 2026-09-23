"""Rate-limit retry, SharePoint query escaping, and name selectors."""

import unittest
from unittest.mock import patch

from core import http
from core.config import filter_workstreams
from core.products import filter_by_product
from core.sources import sharepoint_search_url
from commands.lint import check_issue


class HttpTests(unittest.TestCase):
    def test_retries_a_rate_limit_once(self):
        codes = iter([429, 200])

        class Response:
            def __init__(self, code):
                self.status_code = code
                self.headers = {"Retry-After": "0"}

        def fake(method, url, **kwargs):
            return Response(next(codes))

        with patch("core.http.requests.request", fake), \
                patch("core.http.time.sleep") as slept:
            response = http.send("GET", "https://example.test")
        self.assertEqual(response.status_code, 200)
        slept.assert_called_once_with(0)

    def test_second_rate_limit_fails_clearly(self):
        class Response:
            status_code = 429
            headers = {"Retry-After": "1"}

        with patch("core.http.requests.request", return_value=Response()), \
                patch("core.http.time.sleep"):
            with self.assertRaises(Exception) as caught:
                http.send("GET", "https://example.test")
        self.assertIn("Rate limit (429)", str(caught.exception))


class SharePointTests(unittest.TestCase):
    def test_apostrophe_is_escaped(self):
        url = sharepoint_search_url("site-id", "O'Brien")
        self.assertIn("O%27%27Brien", url)
        self.assertNotIn("O'Brien", url)


class NameFilterTests(unittest.TestCase):
    def test_workstream_full_name_is_accepted(self):
        cfg = {"workstreams": [
            {"name": "Secure Data Exchange", "abbrev": "SDX"},
            {"name": "API Platform", "abbrev": "APS"},
        ]}
        picked = filter_workstreams(cfg, "Secure Data Exchange")
        self.assertEqual([ws["abbrev"] for ws in picked], ["SDX"])

    def test_product_full_name_is_accepted(self):
        cfg = {
            "products": [{"name": "Integration Platform", "abbrev": "IP"}],
            "workstreams": [
                {"name": "Secure Data Exchange", "abbrev": "SDX",
                 "product": "IP"},
            ],
        }
        picked = filter_by_product(cfg, cfg["workstreams"], "integration platform")
        self.assertEqual([ws["abbrev"] for ws in picked], ["SDX"])


def _issue(**overrides):
    issue = {
        "key": "APS-1",
        "url": "http://example/APS-1",
        "summary": "Rotate the exchange signing certificates",
        "issuetype": "Story",
        "status_category": "indeterminate",
        "components": ["API Platform"],
        "epic": "APS-3",
        "acceptance_criteria": "Given a tenant",
        "description": "",
        "story_points": 3,
        "start_date": None,
        "due_date": None,
        "updated": "2026-09-01T00:00:00.000+0000",
        "status_changed": None,
    }
    issue.update(overrides)
    return issue


class VagueTitleTests(unittest.TestCase):
    def test_refactor_inside_a_specific_title_is_not_vague(self):
        findings = check_issue(_issue(summary="Refactor the retry handler"), {
            "min_title_words": 3,
            "vague_title_terms": ["fix"],
            "vague_title_alone": ["refactor", "test"],
            "required_fields": [],
            "require_acceptance_criteria": False,
            "require_estimate": False,
        })
        self.assertFalse(any(f["rule"] == "vague-title" for f in findings))

    def test_a_title_that_is_only_test_is_vague(self):
        findings = check_issue(_issue(summary="test"), {
            "min_title_words": 1,
            "vague_title_terms": [],
            "vague_title_alone": ["test"],
            "required_fields": [],
            "require_acceptance_criteria": False,
            "require_estimate": False,
        })
        self.assertTrue(any(f["rule"] == "vague-title" for f in findings))
