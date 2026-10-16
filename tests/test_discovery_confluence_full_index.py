"""Confluence checkpoint handoff and project-scoped indexing regression tests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import discovery_confluence_checkpoint as checkpoint
from core import discovery_confluence_index as indexer
from core import discovery_fts


class FullConfluenceIndexTests(unittest.TestCase):
    def test_multiple_checkpoint_batches_are_all_indexed_under_team_project(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "index.sqlite"
            cfg = {"jira": {"project": "APS"}, "confluence": {"scopes": [
                {"type": "page_tree", "space_key": "POSM", "page_id": "100"}]}}
            def pages(_cfg, _space, start=0, limit=25, ancestor_id=None):
                self.assertEqual(ancestor_id, "100")
                rows = [{"id": str(n + 101), "title": "Item " + str(n),
                         "type": "page", "ancestors": [{"id": "100"}]}
                        for n in range(start, min(125, start + limit))]
                return rows, start + len(rows) < 125

            def fetch(_cfg, page_id):
                return {"id": page_id, "title": "Page " + page_id,
                        "type": "page", "space": {"key": "POSM"},
                        "body": {"storage": {
                            "value": "<p>Secure Data Exchange source document " +
                            page_id + "</p>"}}}
            with patch.object(checkpoint.sources, "fetch_confluence_page",
                              side_effect=fetch), \
                 patch.object(checkpoint.sources, "list_confluence_inventory",
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
            with sqlite3.connect(str(path)) as db:
                indexed = db.execute(
                    "SELECT COUNT(*) FROM discovery_fts_documents "
                    "WHERE source='confluence' AND project='APS'").fetchone()[0]
            self.assertEqual(indexed, 126)
            hits = discovery_fts.search(path, '"Secure Data Exchange"', project="APS")
            self.assertTrue(hits)

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
