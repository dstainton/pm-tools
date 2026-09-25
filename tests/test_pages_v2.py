"""Confluence reader: types, key matching, body length, and the fetch cache."""

import datetime as dt
import os
import tempfile
import unittest

from core import cache as cache_core
from core import pages
from tests.fake_jira import FakeJira
from tests.test_cli_end_to_end import backlog, pages as fixture_pages


class PagesV2Tests(unittest.TestCase):
    def setUp(self):
        self.jira = FakeJira(backlog(), pages=fixture_pages())
        self.jira.__enter__()
        self.addCleanup(lambda: self.jira.__exit__(None, None, None))
        self.cfg = {
            "jira": {"base_url": self.jira.url, "email": "pm@example.com",
                     "api_token": "token", "project": "APS",
                     "max_results": 50, "page_size": 50},
            "confluence": {
                "base_url": self.jira.url + "/wiki",
                "email": "pm@example.com", "api_token": "token",
                "lookback_days": 7, "max_results": 50,
                "content_types": ["page", "blogpost"],
                "title_only_types": ["database", "embed"],
            },
            "pages": {"scope": "space", "follow_jira_links": True,
                      "summary_chars": 6000, "max_pages": 20},
            "publish": {"confluence": {"space": "APS", "parent_page": "Weekly Reports"}},
            "workstreams": [{"abbrev": "SDX", "project": "APS"}],
        }
        self.ws = {"abbrev": "SDX", "name": "SDX", "confluence_space": "SDX",
                   "confluence_labels": ["decision", "risk"], "product": "IP"}
        self.window = {"start": dt.date.today() - dt.timedelta(days=7), "explicit": False}

    def test_space_read_keeps_types_and_drops_the_rest(self):
        found = pages.gather(self.cfg, self.ws, window=self.window)
        titles = [page["title"] for page in found]
        self.assertIn("SDX runbook index", titles)
        self.assertIn("SDX weekly update", titles)
        self.assertIn("Partner onboarding tracker", titles)
        self.assertNotIn("SDX whiteboard must stay out", titles)
        self.assertNotIn("Ancient decision", titles)
        self.assertNotIn("Decision: rate limit defaults", titles)
        runbook = next(page for page in found if page["title"] == "SDX runbook index")
        self.assertIn("APS-10", runbook["keys"])
        self.assertIn("Last sentence stays.", runbook["body_text"])
        tracker = next(page for page in found if page["type"] == "database")
        self.assertTrue(tracker["title_only"])
        self.assertEqual(tracker["body_text"], "")

    def test_mention_and_remote_link_match_epics(self):
        found = pages.gather(self.cfg, self.ws, window=self.window)
        epic_rows = [{"key": "APS-1", "pages": []}, {"key": "APS-2", "pages": [], "in_scope": True}]
        pages.map_to_epics(found, epic_rows, {"APS-10": "APS-1"}, self.cfg)
        runbook = next(page for page in found if page["title"] == "SDX runbook index")
        self.assertEqual(runbook["epic"], "APS-1")
        self.assertEqual(runbook["epic_match"], "mention")

        aps = {"abbrev": "APS", "name": "APS", "confluence_space": "", "product": "IP"}
        linked = pages.gather(
            self.cfg, aps, epics=[{"key": "APS-2", "in_scope": True}], window=self.window)
        self.assertTrue(any(page["page_id"] == "2002" and page["epic_match"] == "link"
                            for page in linked))

    def test_second_fetch_is_cached(self):
        folder = tempfile.mkdtemp()
        store = cache_core.FetchCache(folder, ttl_seconds=300)
        self.cfg["_fetch_cache"] = store
        pages.gather(self.cfg, self.ws, window=self.window)
        first = [c for c in self.jira.calls if c[0] == "GET" and "content/search" in c[1]]
        pages.gather(self.cfg, self.ws, window=self.window)
        second = [c for c in self.jira.calls if c[0] == "GET" and "content/search" in c[1]]
        self.assertEqual(len(second), len(first))
        self.assertTrue(os.path.isdir(folder))


if __name__ == "__main__":
    unittest.main()
