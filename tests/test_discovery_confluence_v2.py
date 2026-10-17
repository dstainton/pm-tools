"""Confluence v2 descendant API and cursor persistence tests."""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from core import discovery_confluence_checkpoint as cp
from core import sources


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class DescendantClientTests(unittest.TestCase):
    def test_extract_cursor_from_next_link_with_no_followed_arbitrary_url(self):
        cfg = {"confluence": {"base_url": "https://example.atlassian.net/wiki",
                              "email": "user@example.com", "api_token": "placeholder"}}
        response = Response({
            "results": [{"id": "200", "title": "Page", "type": "page"}],
            "_links": {"next": "/wiki/api/v2/pages/100/descendants?limit=100&cursor=abc%2B123%3D"}})
        with patch.object(sources, "send", return_value=response) as send:
            rows, cursor = sources.list_confluence_page_descendants(cfg, "100")
        self.assertEqual(rows[0]["id"], "200")
        self.assertEqual(cursor, "abc+123=")
        self.assertEqual(send.call_args.args[1],
                         "https://example.atlassian.net/wiki/api/v2/pages/100/descendants")
        self.assertEqual(send.call_args.kwargs["params"], {"limit": 100})

        with patch.object(sources, "send", return_value=Response({
                "results": [], "_links": {}})) as send:
            rows, next_cursor = sources.list_confluence_page_descendants(
                cfg, "100", cursor=cursor, limit=40)
        self.assertEqual(rows, [])
        self.assertIsNone(next_cursor)
        self.assertEqual(send.call_args.kwargs["params"],
                         {"limit": 40, "cursor": "abc+123="})

    def test_opaque_continuation_cannot_be_silently_lost(self):
        cfg = {"confluence": {"base_url": "https://example.atlassian.net/wiki",
                              "email": "user@example.com", "api_token": "placeholder"}}
        with patch.object(sources, "send", return_value=Response({
                "results": [{"id": "200", "type": "page"}],
                "_links": {"next": "/wiki/api/v2/pages/100/descendants?limit=100"}})):
            with self.assertRaisesRegex(ValueError, "lacks cursor"):
                sources.list_confluence_page_descendants(cfg, "100")

    def test_resume_after_checkpoint_and_ignore_non_page_descendants(self):
        cfg = {"confluence": {"scopes": [
            {"type": "page_tree", "space_key": "POSM", "page_id": "100"}]}}
        root = {"id": "100", "title": "Team", "space": {"key": "POSM"}}
        first_pages = [
            {"id": "200", "type": "page", "title": "A"},
            {"id": "300", "type": "folder", "title": "Folder"},
            {"id": "400", "type": "page", "title": "Nested page",
             "parentId": "300", "depth": 2}]
        calls = []
        def fetch(_cfg, page_id, cursor=None, limit=100, content_type="page"):
            calls.append((cursor, limit))
            if cursor is None:
                return first_pages, "next-page"
            return [{"id": "500", "type": "page", "title": "Last"}], None
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "index.sqlite"
            with patch.object(cp.sources, "fetch_confluence_page",
                              return_value=root), patch.object(
                                  cp.sources, "list_confluence_page_descendants",
                                  side_effect=fetch):
                first = cp.crawl(cfg, path, max_rows=3)
                with closing(sqlite3.connect(str(path))) as db:
                    self.assertEqual(db.execute(
                        "SELECT cursor FROM confluence_inventory_cursor").fetchone()[0],
                        "next-page")
                second = cp.crawl(cfg, path, max_rows=3)
                self.assertEqual(calls, [(None, 3), ("next-page", 3)])
                self.assertEqual(first[0]["status"], "incomplete")
                self.assertEqual(first[0]["new_pages"], 2)
                self.assertEqual(second[0]["status"], "complete")
                self.assertEqual(second[0]["new_pages"], 1)
                with closing(sqlite3.connect(str(path))) as db:
                    kinds = dict(db.execute(
                        "SELECT content_id,content_type FROM confluence_inventory_items"))
                self.assertEqual(set(kinds), {"100", "200", "400", "500"})
                self.assertEqual(set(kinds.values()), {"page"})


if __name__ == "__main__":
    unittest.main()
