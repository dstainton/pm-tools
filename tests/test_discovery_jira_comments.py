"""Resumable Jira comments and missing permissions."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core import discovery_jira_comments


class Reply:
    def __init__(self, body):
        self.body = body
    def raise_for_status(self):
        pass
    def json(self):
        return self.body


class CommentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "evidence.sqlite"
        db = sqlite3.connect(str(self.path))
        try:
            db.execute("""CREATE TABLE jira_raw_issues
                (project TEXT, issue_key TEXT, payload TEXT,
                 PRIMARY KEY(project, issue_key))""")
            db.execute("INSERT INTO jira_raw_issues VALUES (?, ?, ?)",
                       ("EX", "EX-1", "{}"))
            db.commit()
        finally:
            db.close()
        self.cfg = {"jira": {"base_url": "https://jira.test",
                            "email": "test", "api_token": "token"}}

    def test_pages_and_resume(self):
        first = Reply({"total": 2, "comments": [
            {"id": "1", "body": {"type": "doc"},
             "created": "2025-01-01"}]})
        last = Reply({"total": 2, "comments": [
            {"id": "2", "body": {"type": "doc"},
             "created": "2025-02-01"}]})
        with patch("core.discovery_jira_comments.sources.send",
                   side_effect=[first, last]) as send:
            partial = discovery_jira_comments.collect(self.cfg, self.path)
            complete = discovery_jira_comments.collect(self.cfg, self.path)
        self.assertEqual(partial["coverage"], "partial")
        self.assertEqual(complete["coverage"], "complete")
        self.assertEqual(send.call_args.kwargs["params"]["startAt"], 1)
        db = sqlite3.connect(str(self.path))
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM jira_comments").fetchone()[0], 2)
        finally:
            db.close()

    def test_permission_failure_keeps_pending(self):
        with patch("core.discovery_jira_comments.sources.send",
                   side_effect=PermissionError("forbidden")):
            result = discovery_jira_comments.collect(self.cfg, self.path)
        self.assertEqual(result["remaining"], 1)
        self.assertEqual(result["coverage"], "partial")
