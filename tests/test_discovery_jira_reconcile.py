"""Reconciliation must not turn partial or denied searches into deletions."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core import discovery_jira_reconcile


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "inventory.sqlite"
        db = sqlite3.connect(str(self.path))
        try:
            db.execute("""CREATE TABLE jira_progress
                (project TEXT PRIMARY KEY, complete INTEGER, source_url TEXT)""")
            db.execute("""CREATE TABLE jira_raw_issues
                (project TEXT, issue_key TEXT, payload TEXT,
                PRIMARY KEY(project, issue_key))""")
            db.execute("INSERT INTO jira_progress VALUES ('APS', 1, 'https://jira.example')")
            db.executemany("INSERT INTO jira_raw_issues VALUES (?, ?, '{}')",
                           [("APS", "APS-1"), ("APS", "APS-2")])
            db.commit()
        finally:
            db.close()
        self.cfg = {"jira": {"base_url": "https://jira.example"}}

    def test_complete_search_marks_absence_without_removing_source(self):
        with patch("core.discovery_jira_reconcile.sources.search_issues",
                   return_value={"complete": True, "issues": [{"key": "APS-2"}]}):
            result = discovery_jira_reconcile.reconcile(self.cfg, ["APS"], self.path)
        self.assertEqual(result["projects"][0]["missing_candidates"], 1)
        db = sqlite3.connect(str(self.path))
        try:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM jira_raw_issues").fetchone()[0], 2)
            self.assertEqual(db.execute(
                "SELECT issue_key FROM jira_missing_observations").fetchone()[0], "APS-1")
        finally:
            db.close()

    def test_partial_search_does_not_mark_missing(self):
        with patch("core.discovery_jira_reconcile.sources.search_issues",
                   return_value={"complete": False, "reason": "timeout",
                                 "issues": [{"key": "APS-2"}]}):
            result = discovery_jira_reconcile.reconcile(self.cfg, ["APS"], self.path)
        self.assertEqual(result["coverage"], "partial")
        db = sqlite3.connect(str(self.path))
        try:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM jira_missing_observations").fetchone()[0], 0)
        finally:
            db.close()
