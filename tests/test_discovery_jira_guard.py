"""Jira historical evidence must never cross configured Jira endpoints."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from core import discovery_jira_guard


class JiraGuardTests(unittest.TestCase):
    def test_rejects_other_tenant_and_incomplete_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "db.sqlite"
            db = sqlite3.connect(str(path))
            try:
                db.execute("""CREATE TABLE jira_progress
                    (project TEXT PRIMARY KEY, source_url TEXT, complete INTEGER)""")
                db.execute("INSERT INTO jira_progress VALUES ('APS', 'https://jira.a', 1)")
                with self.assertRaises(ValueError):
                    discovery_jira_guard.check(
                        db, {"jira": {"base_url": "https://jira.b"}})
                discovery_jira_guard.check(
                    db, {"jira": {"base_url": "https://jira.a"}})
                db.execute("UPDATE jira_progress SET complete=0")
                with self.assertRaises(ValueError):
                    discovery_jira_guard.check(
                        db, {"jira": {"base_url": "https://jira.a"}})
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
