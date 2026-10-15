"""Checkpointed Confluence pages beyond the old search cap are indexed."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import discovery_confluence_checkpoint as cp
from core import discovery_confluence_index as ci
from core import discovery_fts


class CheckpointIndexTests(unittest.TestCase):
    def test_completed_inventory_indexes_all_pages(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.sqlite"
            cfg = {"confluence": {"scopes": [{"type": "space", "space_key": "DOC"}]}}
            def pages(cfg, space, start=0, limit=25, ancestor_id=None):
                rows = [{"id": str(n), "title": "Doc " + str(n),
                         "type": "page", "ancestors": []}
                        for n in range(start, min(start + limit, 125))]
                return rows, start + len(rows) < 125
            with patch.object(cp.sources, "list_confluence_inventory", side_effect=pages):
                cp.crawl(cfg, path, max_rows=100)
                cp.crawl(cfg, path, max_rows=100)
            def fetched(cfg, pid):
                return {"id": pid, "space": {"key": "DOC"},
                        "title": "Doc " + pid,
                        "body": {"storage": {"value": "<p>Terminology " + pid + "</p>"}}}
            with patch.object(ci.sources, "fetch_confluence_page", side_effect=fetched):
                with patch.object(ci.sources, "list_confluence_inventory",
                                  return_value=([], False)):
                    with patch.object(ci.sources, "list_confluence_comments",
                                      return_value=([], False)):
                        result = ci.index(cfg, path, use_checkpoint=True)
            self.assertEqual(result["indexed"], 125)
            self.assertTrue(result["complete"])
            self.assertEqual(len(discovery_fts.search(path, "Terminology", limit=100)), 100)

    def test_incomplete_checkpoint_does_not_claim_full_coverage(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.sqlite"
            cfg = {"confluence": {"scopes": [{"type": "space", "space_key": "DOC"}]}}
            with patch.object(cp.sources, "list_confluence_inventory",
                              return_value=([{"id": "123"}], True)):
                cp.crawl(cfg, path, max_rows=1)
            with patch.object(ci.sources, "fetch_confluence_page", return_value={
                "id": "123", "space": {"key": "DOC"}, "title": "Sample"}):
                with patch.object(ci.sources, "list_confluence_inventory",
                                  return_value=([], False)):
                    with patch.object(ci.sources, "list_confluence_comments",
                                      return_value=([], False)):
                        result = ci.index(cfg, path, use_checkpoint=True)
            self.assertEqual(result["indexed"], 1)
            self.assertFalse(result["complete"])


if __name__ == "__main__":
    unittest.main()
