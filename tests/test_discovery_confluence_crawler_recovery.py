"""Regression tests for Confluence deep ancestry, cursor recovery and loops."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from core import discovery_confluence_checkpoint as cp


class ConfluenceCrawlerRecoveryTests(unittest.TestCase):
    def test_legacy_offset_restarts_without_losing_pages_and_accepts_deep_results(self):
        cfg = {"confluence": {"scopes": [
            {"type": "page_tree", "space_key": "POSM", "page_id": "100"}]}}
        scope = {"type": "page_tree", "space": "POSM",
                 "root_id": "100", "root_title": None}
        sid = cp._identity(scope)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "store.sqlite"
            # Reproduce the pre-fix database, including the old schema.
            with closing(sqlite3.connect(str(path))) as db:
                db.execute("""CREATE TABLE confluence_inventory_cursor
                    (scope_id TEXT PRIMARY KEY, scope_json TEXT NOT NULL,
                     offset INTEGER NOT NULL, status TEXT NOT NULL, error TEXT)""")
                db.execute("""CREATE TABLE confluence_inventory_items
                    (scope_id TEXT NOT NULL, content_id TEXT NOT NULL,
                     space TEXT, title TEXT, content_type TEXT,
                     updated TEXT, ancestors TEXT,
                     PRIMARY KEY(scope_id, content_id))""")
                db.execute("INSERT INTO confluence_inventory_cursor VALUES(?,?,?,?,?)",
                           (sid, json.dumps(scope, sort_keys=True),
                            22300, "incomplete", None))
                db.execute("INSERT INTO confluence_inventory_items VALUES(?,?,?,?,?,?,?)",
                           (sid, "900", "POSM", "Previously indexed", "page", None, "[]"))
                db.commit()
            root = {"id": "100", "title": "Team", "space": {"key": "POSM"}}
            starts = []
            def fetch(_cfg, _space, start=0, limit=25, ancestor_id=None):
                starts.append(start)
                return ([
                    {"id": "200", "title": "Deep A",
                     "ancestors": [{"id": "999"}]},
                    {"id": "201", "title": "Deep B", "ancestors": []},
                ], False)
            with patch.object(cp.sources, "fetch_confluence_page",
                              return_value=root):
                with patch.object(cp.sources, "list_confluence_inventory",
                                  side_effect=fetch):
                    result = cp.crawl(cfg, path)
            self.assertEqual(starts, [0])
            self.assertEqual(result[0]["status"], "complete")
            self.assertTrue(result[0]["legacy_checkpoint_restarted"])
            self.assertEqual(result[0]["new_pages"], 2)
            self.assertEqual(result[0]["ancestry_metadata_warnings"], 1)
            with closing(sqlite3.connect(str(path))) as db:
                row = db.execute(
                    "SELECT offset,status,scan_version FROM confluence_inventory_cursor"
                ).fetchone()
                pages = {r[0] for r in db.execute(
                    "SELECT content_id FROM confluence_inventory_items")}
            self.assertEqual(row, (2, "complete", cp.SCAN_VERSION))
            self.assertEqual(pages, {"900", "100", "200", "201"})

    def test_identical_pagination_is_detected_and_checkpoint_preserved(self):
        cfg = {"confluence": {"scopes": [
            {"type": "page_tree", "space_key": "POSM", "page_id": "100"}]}}
        root = {"id": "100", "title": "Team", "space": {"key": "POSM"}}
        calls = []
        def repeat(_cfg, _space, start=0, limit=25, ancestor_id=None):
            calls.append(start)
            return ([{"id": str(i), "title": "Page " + str(i),
                      "ancestors": []} for i in range(200, 225)], True)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "store.sqlite"
            with patch.object(cp.sources, "fetch_confluence_page",
                              return_value=root):
                with patch.object(cp.sources, "list_confluence_inventory",
                                  side_effect=repeat):
                    result = cp.crawl(cfg, path, max_rows=100)
            self.assertEqual(calls, [0, 25])
            self.assertEqual(result[0]["status"], "incomplete")
            self.assertIn("Repeated Confluence results", result[0]["error"])
            self.assertEqual(result[0]["offset"], 25)
            self.assertEqual(result[0]["new_pages"], 25)
            with closing(sqlite3.connect(str(path))) as db:
                checkpoint = db.execute(
                    "SELECT offset,status,error FROM confluence_inventory_cursor"
                ).fetchone()
                retained = db.execute(
                    "SELECT COUNT(*) FROM confluence_inventory_items").fetchone()[0]
            self.assertEqual(checkpoint[0:2], (25, "incomplete"))
            self.assertIn("Repeated", checkpoint[2])
            self.assertEqual(retained, 26)

    def test_completed_parent_covers_children_with_old_or_missing_checkpoints(self):
        cfg = {"confluence": {"scopes": [
            {"type": "page_tree", "space_key": "POSM", "page_id": "100"},
            {"type": "page_tree", "space_key": "POSM",
             "title": "Secure Data Exchange (SDX)"},
            {"type": "page_tree", "space_key": "POSM",
             "title": "Integration Toolkit (ITK)"}]}}
        names = {"100": "API Program Services (APS) Team",
                 "200": "Secure Data Exchange (SDX)",
                 "300": "Integration Toolkit (ITK)"}
        def fetch(_cfg, page_id):
            return {"id": page_id, "title": names[page_id],
                    "space": {"key": "POSM"}}
        def search(_cfg, space, title):
            return [{"id": identifier} for identifier, name in names.items()
                    if name == title]
        calls = []
        def search_pages(_cfg, space, start=0, limit=25, ancestor_id=None):
            calls.append((start, ancestor_id))
            self.assertEqual(ancestor_id, "100")
            return ([
                {"id": "200", "title": names["200"], "ancestors": []},
                {"id": "300", "title": names["300"],
                 "ancestors": [{"id": "999"}]},
                {"id": "400", "title": "Nested architecture page",
                 "ancestors": []}], False)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "store.sqlite"
            # The SDX scope already has a broken v1 checkpoint, as in APS.
            child = {"type": "page_tree", "space": "POSM",
                     "root_id": "200", "root_title": "Secure Data Exchange (SDX)"}
            with closing(sqlite3.connect(str(path))) as db:
                cp._init(db)
                db.execute("""INSERT INTO confluence_inventory_cursor
                    (scope_id,scope_json,offset,status,error,scan_version)
                    VALUES(?,?,?,?,NULL,1)""",
                    (cp._identity(child), json.dumps(child, sort_keys=True),
                     22300, "incomplete"))
                db.commit()
            with patch.object(cp.sources, "fetch_confluence_page",
                              side_effect=fetch):
                with patch.object(cp.sources, "search_confluence_by_title",
                                  side_effect=search):
                    with patch.object(cp.sources, "list_confluence_inventory",
                                      side_effect=search_pages):
                        results = cp.crawl(cfg, path)
            self.assertEqual(calls, [(0, "100")])
            self.assertEqual([x["status"] for x in results],
                             ["complete", "complete", "complete"])
            self.assertEqual([x.get("covered_by") for x in results[1:]],
                             ["100", "100"])
            indexed = cp.indexed_inventory(cfg, path)
            self.assertEqual(indexed["coverage"], "complete")
            self.assertEqual({x["id"] for x in indexed["pages"]},
                             {"100", "200", "300", "400"})
            self.assertTrue(all(x["status"] == "complete"
                                for x in indexed["scopes"]))


if __name__ == "__main__":
    unittest.main()
