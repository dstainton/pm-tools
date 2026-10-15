"""Checkpointed Confluence collection remains scoped and resumable."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import discovery_confluence_checkpoint as cp


class CheckpointTests(unittest.TestCase):
    def test_resume_without_duplication(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "store.sqlite"
            cfg = {"confluence": {"scopes": [{"type": "space", "space_key": "DOC"}]}}
            seen = []
            def fake_list(cfg, space, start=0, limit=25, ancestor_id=None):
                seen.append(start)
                rows = [{"id": str(n), "title": "Page " + str(n),
                         "type": "page", "ancestors": []}
                        for n in range(start, min(start + limit, 5))]
                return rows, start + len(rows) < 5
            with patch.object(cp.sources, "list_confluence_inventory",
                              side_effect=fake_list):
                first = cp.crawl(cfg, path, max_rows=2)
                second = cp.crawl(cfg, path, max_rows=2)
                third = cp.crawl(cfg, path, max_rows=2)
                fourth = cp.crawl(cfg, path, max_rows=2)
            self.assertEqual(seen, [0, 2, 4])
            self.assertEqual([x[0]["status"] for x in (
                first, second, third, fourth)],
                ["incomplete", "incomplete", "complete", "complete"])
            db = sqlite3.connect(str(path))
            try:
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM confluence_inventory_items").fetchone()[0], 5)
            finally:
                db.close()

    def test_tree_does_not_store_siblings(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "store.sqlite"
            cfg = {"confluence": {"scopes": [
                {"type": "page_tree", "space_key": "DOC", "page_id": "1"}]}}
            root = {"id": "1", "title": "Root", "space": {"key": "DOC"}}
            rows = [{"id": "2", "ancestors": [{"id": "1"}]},
                    {"id": "3", "ancestors": [{"id": "999"}]}]
            with patch.object(cp.sources, "fetch_confluence_page",
                              return_value=root):
                with patch.object(cp.sources, "list_confluence_inventory",
                                  return_value=(rows, False)):
                    result = cp.crawl(cfg, path)
            self.assertEqual(result[0]["status"], "complete")
            db = sqlite3.connect(str(path))
            try:
                ids = {x[0] for x in db.execute(
                    "SELECT content_id FROM confluence_inventory_items")}
                self.assertEqual(ids, {"1", "2"})
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
