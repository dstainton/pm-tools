"""Offline search indexes source observations without modifying Jira tables."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from core import discovery_fts


class FtsTests(unittest.TestCase):
    def test_index_search_and_idempotent_updates(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "jira.sqlite"
            db = sqlite3.connect(str(path))
            try:
                db.execute("""CREATE TABLE jira_raw_issues (
                    project TEXT, issue_key TEXT, payload TEXT,
                    PRIMARY KEY(project, issue_key))""")
                db.execute("""CREATE TABLE jira_comments (
                    issue_key TEXT, comment_id TEXT, payload TEXT,
                    PRIMARY KEY(issue_key, comment_id))""")
                db.execute("""CREATE TABLE jira_history_events (
                    issue_key TEXT, history_id TEXT, field_name TEXT,
                    old_value TEXT, new_value TEXT, event_time TEXT)""")
                issue = {"key": "APS-1", "fields": {"summary": "API gateway",
                    "description": {"type": "doc", "content": [
                        {"type": "paragraph", "content": [
                            {"type": "text", "text": "Kong access policies"}]}]},
                    "labels": ["api"], "components": [{"name": "Platform"}],
                    "created": "2026-01-01", "updated": "2026-02-01"}}
                db.execute("INSERT INTO jira_raw_issues VALUES (?, ?, ?)",
                           ("APS", "APS-1", json.dumps(issue)))
                comment = {"body": {"content": [{"type": "paragraph",
                    "content": [{"type": "text", "text": "OAuth integration"}]}]},
                    "created": "2026-02-02"}
                db.execute("INSERT INTO jira_comments VALUES (?, ?, ?)",
                           ("APS-1", "100", json.dumps(comment)))
                db.execute("INSERT INTO jira_history_events VALUES (?, ?, ?, ?, ?, ?)",
                           ("APS-1", "2:0", "labels", "SDX", "APS P2P", "2025-01-01"))
                db.commit()
            finally:
                db.close()
            first = discovery_fts.index_jira(path)
            second = discovery_fts.index_jira(path)
            self.assertEqual(first["documents_total"], 3)
            self.assertEqual(second["documents_updated"], 0)
            matches = discovery_fts.search(path, "OAuth", kind="comment")
            self.assertEqual(matches[0]["citation"], "jira:APS-1#comment-100")
            self.assertEqual(discovery_fts.search(path, '"APS P2P"', kind="change")[0]["kind"],
                             "change")
            self.assertFalse(discovery_fts.search(path, "OAuth", project="OTHER"))
            db = sqlite3.connect(str(path))
            try:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM jira_raw_issues").fetchone()[0], 1)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
