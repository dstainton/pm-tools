import os
import tempfile
import time
import unittest
from unittest.mock import patch

from core import cache as cache_core
from core import sources


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FetchCacheTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="pm-cache-")
        self.cache = cache_core.FetchCache(self.dir, ttl_seconds=60)

    def test_miss_then_hit(self):
        self.assertIsNone(self.cache.get("abc"))
        self.cache.put("abc", [{"key": "APS-1"}])
        self.assertEqual(self.cache.get("abc"), [{"key": "APS-1"}])
        self.assertEqual(self.cache.entry_count(), 1)

    def test_expired_entry_is_ignored_unless_cached_mode(self):
        stale = cache_core.FetchCache(self.dir, ttl_seconds=0)
        stale.put("abc", ["old"])
        time.sleep(0.02)
        self.assertIsNone(stale.get("abc"))
        stale.mode = "cached"
        self.assertEqual(stale.get("abc"), ["old"])

    def test_refresh_mode_never_returns_a_hit(self):
        self.cache.put("abc", ["old"])
        self.cache.mode = "refresh"
        self.assertIsNone(self.cache.get("abc"))


class SearchCacheTests(unittest.TestCase):
    def test_search_issues_stores_and_reuses_a_page(self):
        tmp = tempfile.mkdtemp(prefix="pm-cache-")
        cfg = {
            "base_url": "https://example.atlassian.net/",
            "email": "pm@example.com",
            "api_token": "token",
            "max_results": 100,
            "page_size": 50,
            "_fetch_cache": cache_core.FetchCache(tmp, ttl_seconds=60),
        }
        response = FakeResponse({"issues": [{"key": "APS-1"}]})
        with patch("core.sources.requests.post", return_value=response) as post:
            first = sources.search_issues(cfg, 'project = "APS"', fields=["key"])
            second = sources.search_issues(cfg, 'project = "APS"', fields=["key"])
        self.assertEqual(first, [{"key": "APS-1"}])
        self.assertEqual(second, first)
        self.assertEqual(post.call_count, 1)


class AttachTests(unittest.TestCase):
    def test_attach_honours_disabled(self):
        cfg = {"cache": {"enabled": False}, "jira": {}}
        self.assertIsNone(cache_core.attach(cfg))
        self.assertNotIn("_fetch_cache", cfg["jira"])

    def test_status_line_reports_empty_and_warm(self):
        tmp = tempfile.mkdtemp(prefix="pm-cache-")
        cfg = {"cache": {"path": tmp, "ttl_seconds": 60}, "jira": {}}
        cache = cache_core.attach(cfg)
        path, count, state = cache_core.status_line(cfg)
        self.assertEqual(state, "empty")
        cache.put("x", [])
        _path, count, state = cache_core.status_line(cfg)
        self.assertEqual(count, 1)
        self.assertEqual(state, "warm")


if __name__ == "__main__":
    unittest.main()
