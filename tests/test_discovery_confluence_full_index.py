"""Confluence checkpoint handoff and project-scoped indexing regression tests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from argparse import Namespace
from contextlib import closing
from unittest.mock import patch

from core import discovery_confluence_checkpoint as checkpoint
from core import discovery_confluence_index as indexer
from core import discovery_fts
from commands import discover


class FullConfluenceIndexTests(unittest.TestCase):
    def test_multiple_checkpoint_batches_are_all_indexed_under_team_project(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "index.sqlite"
            cfg = {"jira": {"project": "APS"}, "confluence": {"scopes": [
                {"type": "page_tree", "space_key": "POSM", "page_id": "100"}]}}
            def pages(_cfg, page_id, cursor=None, limit=100):
                self.assertEqual(page_id, "100")
                start = int(cursor) if cursor else 0
                rows = [{"id": str(n + 101), "title": "Item " + str(n),
                         "type": "page", "ancestors": [{"id": "100"}]}
                        for n in range(start, min(125, start + limit))]
                next_cursor = str(start + len(rows)) if start + len(rows) < 125 else None
                return rows, next_cursor
            def fetch(_cfg, page_id):
                return {"id": page_id, "title": "Page " + page_id,
                        "type": "page", "space": {"key": "POSM"},
                        "body": {"storage": {
                            "value": "<p>Secure Data Exchange source document " +
                            page_id + "</p>"}}}
            with patch.object(checkpoint.sources, "fetch_confluence_page",
                              side_effect=fetch), \
                 patch.object(checkpoint.sources, "list_confluence_page_descendants",
                              side_effect=pages), \
                 patch.object(indexer.sources, "list_confluence_comments",
                              return_value=([], False)):
                first = checkpoint.crawl(cfg, path, max_rows=100)
                second = checkpoint.crawl(cfg, path, max_rows=100)
                result = indexer.index(cfg, path)
            self.assertEqual(first[0]["status"], "incomplete")
            self.assertEqual(second[0]["status"], "complete")
            self.assertEqual(result["inventory_mode"], "checkpoint")
            self.assertEqual(result["indexed"], 126)
            self.assertTrue(result["complete"])
            self.assertEqual(result["project_assignment"], "APS")
            with closing(sqlite3.connect(str(path))) as db:
                indexed = db.execute(
                    "SELECT COUNT(*) FROM discovery_fts_documents "
                    "WHERE source='confluence' AND project='APS'").fetchone()[0]
            self.assertEqual(indexed, 126)
            hits = discovery_fts.search(path, '"Secure Data Exchange"', project="APS")
            self.assertTrue(hits)

    def test_explicit_crawl_and_index_resumes_until_complete(self):
        cfg = {"jira": {"project": "APS"}, "products": [], "workstreams": []}
        incomplete = [{"scope": {"type": "page_tree", "root_id": "100"},
                       "status": "incomplete", "offset": 100, "processed": 100}]
        complete = [{"scope": {"type": "page_tree", "root_id": "100"},
                     "status": "complete", "offset": 125, "processed": 25}]
        args = Namespace(project="APS", confluence_crawl=True,
                         index_confluence=True, export=False)
        with tempfile.TemporaryDirectory() as folder, \
             patch("core.paths.local_dir", return_value=folder), \
             patch("core.discovery_confluence_checkpoint.crawl",
                   side_effect=[incomplete, complete]) as crawler, \
             patch("core.discovery_confluence_index.index",
                   return_value={"indexed": 0, "comments_indexed": 0,
                                 "changed": 0, "comments_changed": 0,
                                 "inventory_coverage": "complete",
                                 "complete": True, "errors": [], "scopes": []}) as index, \
             patch("builtins.print"):
            discover.run(cfg, args)
        self.assertEqual(crawler.call_count, 2)
        index.assert_called_once()

    def test_whole_space_scope_not_attributed_to_a_jira_project(self):
        cfg = {"jira": {"project": "APS"}}
        inventory = {"scopes": [{"type": "space", "space": "POSM",
                                  "status": "complete"}]}
        self.assertIsNone(indexer._single_scoped_project(cfg, inventory))
        multi = {"jira": {"project": "APS"}, "products": [
            {"name": "Other", "project": "OTHER"}]}
        scoped = {"scopes": [{"scope": {"type": "page_tree",
                                       "root_id": "100", "space": "POSM"},
                              "status": "complete"}]}
        self.assertIsNone(indexer._single_scoped_project(multi, scoped))


if __name__ == "__main__":
    unittest.main()
