"""Folder-root routing, node coverage and v3 checkpoint recovery."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from core import discovery_confluence_checkpoint as cp
from core import sources


class FolderRootTests(unittest.TestCase):
    def test_folder_root_fetches_folder_descendants_not_page_descendants(self):
        cfg = {"confluence": {"scopes": [
            {"type": "page_tree", "space_key": "POSM", "page_id": "200"}]}}
        root = {"id": "200", "title": "Secure Data Exchange",
                "type": "folder", "space": {"key": "POSM"}}
        calls = []
        def descend(_cfg, page_id, cursor=None, limit=100, content_type="page"):
            calls.append((page_id, cursor, content_type))
            return ([
                {"id": "300", "type": "folder", "title": "Architecture"},
                {"id": "301", "type": "page", "title": "Decision",
                 "parentId": "300", "depth": 2}], None)
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "index.sqlite"
            with patch.object(cp.sources, "fetch_confluence_page",
                              return_value=root), patch.object(
                                  cp.sources, "list_confluence_page_descendants",
                                  side_effect=descend):
                result = cp.crawl(cfg, db_path)
            self.assertEqual(calls, [("200", None, "folder")])
            self.assertEqual(result[0]["status"], "complete")
            self.assertEqual(result[0]["new_pages"], 1)
            inventory = cp.indexed_inventory(cfg, db_path)
            self.assertEqual([x["id"] for x in inventory["pages"]], ["301"])
            with closing(sqlite3.connect(str(db_path))) as db:
                self.assertEqual(set(db.execute(
                    "SELECT content_id, content_type FROM confluence_inventory_nodes")),
                    {("200", "folder"), ("300", "folder"), ("301", "page")})

    def test_completed_parent_covers_nested_folder_root(self):
        cfg = {"confluence": {"scopes": [
            {"type": "page_tree", "space_key": "POSM", "page_id": "100"},
            {"type": "page_tree", "space_key": "POSM",
             "title": "Secure Data Exchange (SDX)"},
            {"type": "page_tree", "space_key": "POSM",
             "title": "Integration Toolkit (ITK)"}]}}
        types = {"100": "page", "200": "folder", "300": "folder"}
        titles = {"100": "APS Team", "200": "Secure Data Exchange (SDX)",
                  "300": "Integration Toolkit (ITK)"}
        def fetch(_cfg, id_):
            return {"id": id_, "title": titles[id_], "type": types[id_],
                    "space": {"key": "POSM"}}
        calls = []
        def descend(_cfg, page_id, cursor=None, limit=100, content_type="page"):
            calls.append((page_id, content_type))
            if page_id != "100":
                raise AssertionError("Nested folder scopes must be covered by APS")
            return ([
                {"id": "200", "title": titles["200"], "type": "folder"},
                {"id": "300", "title": titles["300"], "type": "folder"},
                {"id": "400", "title": "Shared architecture", "type": "page",
                 "parentId": "200", "depth": 3}], None)
        def search(_cfg, space, title):
            return [{"id": id_} for id_, name in titles.items() if title == name]
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "index.sqlite"
            with patch.object(cp.sources, "fetch_confluence_page",
                              side_effect=fetch), patch.object(
                                  cp.sources, "search_confluence_by_title",
                                  side_effect=search), patch.object(
                                      cp.sources, "list_confluence_page_descendants",
                                      side_effect=descend):
                result = cp.crawl(cfg, db_path)
            self.assertEqual(calls, [("100", "page")])
            self.assertEqual([x["status"] for x in result],
                             ["complete", "complete", "complete"])
            self.assertEqual([x["covered_by"] for x in result[1:]], ["100", "100"])
            inventory = cp.indexed_inventory(cfg, db_path)
            self.assertEqual(inventory["coverage"], "complete")
            self.assertEqual({p["id"] for p in inventory["pages"]}, {"100", "400"})

    def test_existing_completed_v3_folder_scope_is_rechecked_and_nonpages_excluded(self):
        cfg = {"confluence": {"scopes": [
            {"type": "page_tree", "space_key": "POSM", "page_id": "200"}]}}
        scope = {"type": "page_tree", "space": "POSM",
                 "root_id": "200", "root_title": None}
        sid = cp._identity(scope)
        root = {"id": "200", "title": "Secure Data Exchange",
                "type": "folder", "space": {"key": "POSM"}}
        with tempfile.TemporaryDirectory() as folder:
            db_path = Path(folder) / "index.sqlite"
            with closing(sqlite3.connect(str(db_path))) as db:
                cp._init(db)
                db.execute("""INSERT INTO confluence_inventory_cursor
                    (scope_id,scope_json,offset,status,error,scan_version,cursor)
                    VALUES(?,?,?,?,NULL,3,NULL)""",
                    (sid, json.dumps(scope, sort_keys=True), 12, "complete"))
                db.execute("""INSERT INTO confluence_inventory_items
                    (scope_id,content_id,space,title,content_type,updated,ancestors)
                    VALUES(?,?,?,?,?,?,?)""",
                    (sid, "200", "POSM", "Folder root", "folder", None, "[]"))
                db.commit()
            with patch.object(cp.sources, "fetch_confluence_page",
                              return_value=root), patch.object(
                                  cp.sources, "list_confluence_page_descendants",
                                  return_value=([{"id": "301", "type": "page",
                                                 "title": "Information"}], None)
                              ) as call:
                result = cp.crawl(cfg, db_path)
            self.assertEqual(call.call_count, 1)
            self.assertTrue(result[0]["legacy_checkpoint_restarted"])
            self.assertEqual(result[0]["status"], "complete")
            self.assertEqual([x["id"] for x in cp.indexed_inventory(cfg, db_path)["pages"]],
                             ["301"])
            with closing(sqlite3.connect(str(db_path))) as db:
                self.assertEqual(db.execute(
                    "SELECT scan_version,offset,status FROM confluence_inventory_cursor"
                ).fetchone(), (cp.SCAN_VERSION, 1, "complete"))


class FolderEndpointTests(unittest.TestCase):
    def test_type_specific_descendant_url(self):
        cfg = {"confluence": {"base_url": "https://example.atlassian.net/wiki",
                              "email": "u@example.com", "api_token": "test"}}
        class FakeResponse:
            def raise_for_status(self):
                pass
            def json(self):
                return {"results": [], "_links": {}}
        with patch.object(sources, "send", return_value=FakeResponse()) as send:
            sources.list_confluence_page_descendants(
                cfg, "200", content_type="folder")
        self.assertEqual(send.call_args.args[1],
            "https://example.atlassian.net/wiki/api/v2/folders/200/descendants")
        with self.assertRaisesRegex(ValueError, "Unsupported Confluence"):
            sources.list_confluence_page_descendants(
                cfg, "200", content_type="not-a-page")


if __name__ == "__main__":
    unittest.main()
