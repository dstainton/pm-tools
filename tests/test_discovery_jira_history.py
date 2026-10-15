"""Historical Jira classification observation tests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import discovery_jira_history


class Response:
    def __init__(self, value):
        self.value = value

    def raise_for_status(self):
        pass

    def json(self):
        return self.value


class JiraHistoryTests(unittest.TestCase):
    def test_records_historical_fields_and_resumes(self):
        cfg = {"jira": {"base_url": "https://jira.example", "email": "a", "api_token": "t"}}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "evidence.sqlite"
            db = sqlite3.connect(str(path))
            try:
                db.execute("""CREATE TABLE jira_progress (project TEXT PRIMARY KEY, source_url TEXT, complete INTEGER)""")
            db.execute("INSERT INTO jira_progress VALUES (?, ?, ?)", ("EX" if "comments" in "tests/test_discovery_jira_history.py" else "APS", "https://jira.test" if "comments" in "tests/test_discovery_jira_history.py" else "https://jira.example", 1))
            db.execute("""CREATE TABLE jira_raw_issues (
                    project TEXT, issue_key TEXT, payload TEXT,
                    PRIMARY KEY(project, issue_key))""")
                db.execute("INSERT INTO jira_raw_issues VALUES (?, ?, ?)",
                           ("APS", "APS-1", "{}"))
                db.commit()
            finally:
                db.close()
            first = Response({"values": [{
                "id": "77", "created": "2025-01-01",
                "items": [{"field": "labels", "fromString": "SDX",
                           "toString": "APS P2P"},
                          {"field": "status", "fromString": "Open",
                           "toString": "Done"}]}],
                "total": 2, "isLast": False})
            second = Response({"values": [{
                "id": "78", "created": "2025-02-01",
                "items": [{"field": "components", "fromString": "Legacy",
                           "toString": "Gateway"}]}],
                "total": 2, "isLast": True})
            with patch("core.discovery_jira_history.sources.send",
                       side_effect=[first, second]) as send:
                partial = discovery_jira_history.collect(cfg, path, max_issues=1)
                done = discovery_jira_history.collect(cfg, path, max_issues=1)
            self.assertEqual(partial["coverage"], "partial")
            self.assertEqual(done["coverage"], "complete")
            self.assertEqual(send.call_args.kwargs["params"]["startAt"], 1)
            db = sqlite3.connect(str(path))
            try:
                events = db.execute(
                    "SELECT field_name, old_value, new_value FROM jira_history_events ORDER BY history_id").fetchall()
            finally:
                db.close()
            self.assertEqual(len(events), 3)
            self.assertEqual(events[0], ("labels", "SDX", "APS P2P"))
            self.assertEqual(events[-1], ("components", "Legacy", "Gateway"))

    def test_unavailable_history_is_reported(self):
        cfg = {"jira": {"base_url": "https://jira.example", "email": "a", "api_token": "t"}}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "evidence.sqlite"
            db = sqlite3.connect(str(path))
            try:
                db.execute("""CREATE TABLE jira_raw_issues (
                    project TEXT, issue_key TEXT, payload TEXT,
                    PRIMARY KEY(project, issue_key))""")
                db.execute("INSERT INTO jira_raw_issues VALUES (?, ?, ?)",
                           ("APS", "APS-2", "{}"))
                db.commit()
            finally:
                db.close()
            with patch("core.discovery_jira_history.sources.send",
                       side_effect=PermissionError("restricted")):
                result = discovery_jira_history.collect(cfg, path)
            self.assertEqual(result["coverage"], "partial")
            self.assertEqual(result["remaining"], 1)
            self.assertEqual(result["errors"][0]["issue"], "APS-2")


if __name__ == "__main__":
    unittest.main()
