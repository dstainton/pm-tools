"""Read-only Confluence draft classification and v2 published-content fallback."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from core import discovery_confluence_checkpoint as cp
from core import discovery_confluence_index as idx
from core import discovery_fts, sources


class PageResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self.payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ValueError("Unexpected HTTP error " + str(self.status_code))

    def json(self):
        return self.payload


class StatusProbeTests(unittest.TestCase):
    def test_draft_probe_is_metadata_only(self):
        cfg = {"confluence": {"base_url": "https://example.atlassian.net/wiki",
                              "email": "test@example.org", "api_token": "fake"}}
        with patch.object(sources, "send", return_value=PageResponse(
                200, {"id": "201", "status": "draft"})) as send:
            page = sources.fetch_confluence_page_v2(cfg, "201", get_draft=True)
        self.assertEqual(page["status"], "draft")
        self.assertEqual(send.call_args.kwargs["params"], {"get-draft": "true"})
        self.assertEqual(send.call_args.args[1],
                         "https://example.atlassian.net/wiki/api/v2/pages/201")

    def test_404_is_unknown_not_assumed_draft(self):
        cfg = {"confluence": {"base_url": "https://example.atlassian.net/wiki",
                              "email": "test@example.org", "api_token": "fake"}}
        with patch.object(sources, "send", return_value=PageResponse(404)):
            self.assertIsNone(sources.fetch_confluence_page_v2(cfg, "201"))
            self.assertIsNone(sources.fetch_confluence_page_v2(
                cfg, "201", get_draft=True))


class IndexStatusTests(unittest.TestCase):
    def _database(self, path, ids):
        scope = {"type": "page_tree", "space": "POSM",
                 "root_id": "100", "root_title": None}
        sid = cp._identity(scope)
        with closing(sqlite3.connect(str(path))) as db:
            cp._init(db)
            db.execute("""INSERT INTO confluence_inventory_cursor
                (scope_id,scope_json,offset,status,error,scan_version,cursor)
                VALUES(?,?,?,?,NULL,4,NULL)""",
                (sid, json.dumps(scope, sort_keys=True), len(ids), "complete"))
            for pid in ids:
                db.execute("""INSERT INTO confluence_inventory_items
                    (scope_id,content_id,space,title,content_type,updated,ancestors,status)
                    VALUES(?,?,?,?,?,?,?,?)""",
                    (sid, pid, "POSM", "Page " + pid, "page", None, "[]", None))
            db.commit()

    def test_draft_only_page_is_excluded_and_complete(self):
        cfg = {"jira": {"project": "APS"},
               "confluence": {"scopes": [
                   {"type": "page_tree", "space_key": "POSM", "page_id": "100"}]}}
        calls = []
        def v1(_cfg, pid):
            if pid == "100":
                return {"id": pid, "status": "current", "title": "Team",
                        "space": {"key": "POSM"},
                        "body": {"storage": {"value": "published"}}}
            return None
        def v2(_cfg, pid, get_draft=False, body_format=None):
            calls.append((pid, get_draft, body_format))
            if not get_draft:
                return None
            return {"id": pid, "status": "draft", "title": "Unpublished"}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "store.sqlite"
            self._database(path, ["100", "201"])
            with patch.object(sources, "fetch_confluence_page", side_effect=v1), \
                 patch.object(sources, "fetch_confluence_page_v2", side_effect=v2), \
                 patch.object(sources, "list_confluence_comments",
                              return_value=([], False)):
                report = idx.index(cfg, path)
            self.assertTrue(report["complete"])
            self.assertEqual(report["indexed"], 1)
            self.assertEqual(report["drafts_skipped"], [
                {"id": "201", "title": "Page 201"}])
            self.assertEqual(report["errors"], [])
            self.assertEqual(calls, [
                ("201", False, "storage"), ("201", True, None)])
            with closing(sqlite3.connect(str(path))) as db:
                self.assertEqual(db.execute(
                    "SELECT status FROM confluence_inventory_items WHERE content_id='201'"
                ).fetchone()[0], "draft")
                indexed = db.execute(
                    "SELECT source_key FROM discovery_fts_documents"
                ).fetchall()
            self.assertEqual(indexed, [("100",)])

    def test_published_v2_fallback_and_unknown_are_distinguished(self):
        cfg = {"jira": {"project": "APS"},
               "confluence": {"scopes": [
                   {"type": "page_tree", "space_key": "POSM", "page_id": "100"}]}}
        def v1(_cfg, pid):
            return {"id": pid, "title": "Team", "space": {"key": "POSM"},
                    "body": {"storage": {"value": "published"}}} if pid == "100" else None
        def v2(_cfg, pid, get_draft=False, body_format=None):
            if pid == "202" and not get_draft:
                return {"id": pid, "status": "current", "title": "Current v2",
                        "body": {"storage": {"value": "<p>API platform policy</p>"}},
                        "version": {"createdAt": "2026-10-16T00:00:00Z"}}
            return None
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "store.sqlite"
            self._database(path, ["100", "202", "203"])
            with patch.object(sources, "fetch_confluence_page", side_effect=v1), \
                 patch.object(sources, "fetch_confluence_page_v2", side_effect=v2), \
                 patch.object(sources, "list_confluence_comments",
                              return_value=([], False)):
                report = idx.index(cfg, path)
            self.assertEqual(report["indexed"], 2)
            self.assertEqual(report["v2_fallbacks"], [
                {"id": "202", "title": "Page 202"}])
            self.assertEqual(report["drafts_skipped"], [])
            self.assertEqual(len(report["errors"]), 1)
            self.assertEqual(report["errors"][0]["id"], "203")
            self.assertIn("draft status not confirmed", report["errors"][0]["detail"])
            with closing(sqlite3.connect(str(path))) as db:
                found = db.execute(
                    "SELECT body FROM discovery_fts_documents WHERE source_key='202'"
                ).fetchone()
            self.assertEqual(found[0], "API platform policy")

    def test_no_draft_body_if_metadata_status_is_draft(self):
        calls = []
        def v2(_cfg, pid, get_draft=False, body_format=None):
            calls.append((get_draft, body_format))
            return {"id": pid, "status": "draft", "title": "Private draft"}
        with patch.object(sources, "fetch_confluence_page_v2", side_effect=v2):
            document, status = idx._published_v2_fallback({}, "201")
        self.assertIsNone(document)
        self.assertEqual(status, "draft")
        self.assertEqual(calls, [(False, "storage")])


if __name__ == "__main__":
    unittest.main()
