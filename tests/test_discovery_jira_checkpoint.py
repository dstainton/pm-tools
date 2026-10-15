"""Transactional Jira crawl checkpoint coverage."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import discovery_jira_checkpoint


class Response:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class CheckpointTests(unittest.TestCase):
    def test_interrupt_and_resume_without_refetching_first_page(self):
        cfg = {"jira": {"base_url": "https://jira.example", "email": "x", "api_token": "y"}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "crawl.sqlite"
            first = Response({"issues": [{"key": "APS-1", "fields": {}}],
                              "nextPageToken": "next"})
            final = Response({"issues": [{"key": "APS-2", "fields": {}}]})
            with patch("core.discovery_jira_checkpoint.sources.send", return_value=first):
                updates = []
                partial = discovery_jira_checkpoint.crawl(cfg, ["APS"], path, page_limit=1,
                    on_progress=lambda project, stored, pages, complete:
                    updates.append((project, stored, pages, complete)))
            self.assertEqual(updates, [("APS", 1, 1, False)])
            self.assertEqual(partial["coverage"], "partial")
            with patch("core.discovery_jira_checkpoint.sources.send", return_value=final) as send:
                complete = discovery_jira_checkpoint.crawl(cfg, ["APS"], path)
            self.assertEqual(complete["coverage"], "complete")
            self.assertEqual(complete["projects"][0]["stored"], 2)
            self.assertEqual(send.call_args.kwargs["json"]["nextPageToken"], "next")
            with patch("core.discovery_jira_checkpoint.sources.send") as send:
                discovery_jira_checkpoint.crawl(cfg, ["APS"], path)
            send.assert_not_called()

    def test_failed_next_page_keeps_checkpoint(self):
        cfg = {"jira": {"base_url": "https://jira.example", "email": "x", "api_token": "y"}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "crawl.sqlite"
            with patch("core.discovery_jira_checkpoint.sources.send",
                       return_value=Response({"issues": [{"key": "APS-1"}],
                                              "nextPageToken": "t"})):
                discovery_jira_checkpoint.crawl(cfg, ["APS"], path, page_limit=1)
            with patch("core.discovery_jira_checkpoint.sources.send",
                       side_effect=ConnectionError("offline")):
                result = discovery_jira_checkpoint.crawl(cfg, ["APS"], path)
            self.assertEqual(result["coverage"], "partial")
            self.assertEqual(result["projects"][0]["stored"], 1)


    def test_checkpoint_rejects_different_jira_endpoint(self):
        cfg = {"jira": {"base_url": "https://jira.example", "email": "x", "api_token": "y"}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "crawl.sqlite"
            with patch("core.discovery_jira_checkpoint.sources.send",
                       return_value=Response({"issues": [{"key": "APS-1"}],
                                              "nextPageToken": "more"})):
                discovery_jira_checkpoint.crawl(cfg, ["APS"], path, page_limit=1)
            changed = {"jira": dict(cfg["jira"], base_url="https://other.example")}
            with patch("core.discovery_jira_checkpoint.sources.send") as send:
                result = discovery_jira_checkpoint.crawl(changed, ["APS"], path)
            self.assertEqual(result["coverage"], "partial")
            self.assertEqual(result["projects"][0]["status"], "unavailable")
            send.assert_not_called()


    def test_refresh_only_after_complete_baseline(self):
        cfg = {"jira": {"base_url": "https://jira.example", "email": "x", "api_token": "y"}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "crawl.sqlite"
            with patch("core.discovery_jira_checkpoint.sources.search_issues") as search:
                result = discovery_jira_checkpoint.refresh(cfg, ["APS"], path)
            self.assertEqual(result["coverage"], "partial")
            search.assert_not_called()

    def test_refresh_updates_issues_and_rejects_partial_results(self):
        import sqlite3
        cfg = {"jira": {"base_url": "https://jira.example", "email": "x", "api_token": "y"}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "crawl.sqlite"
            with patch("core.discovery_jira_checkpoint.sources.send",
                       return_value=Response({"issues": [{"key": "APS-1",
                           "fields": {"updated": "2026-10-01T00:00:00Z"}}]})):
                discovery_jira_checkpoint.crawl(cfg, ["APS"], path)
            with patch("core.discovery_jira_checkpoint.sources.search_issues",
                       return_value={"issues": [{"key": "APS-2",
                           "fields": {"updated": "2026-10-02T00:00:00Z"}}],
                           "complete": False, "reason": "timeout"}):
                partial = discovery_jira_checkpoint.refresh(cfg, ["APS"], path)
            self.assertEqual(partial["coverage"], "partial")
            db = sqlite3.connect(str(path))
            try:
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM jira_raw_issues").fetchone()[0], 1)
                self.assertIsNone(db.execute(
                    "SELECT refreshed_at FROM jira_progress").fetchone()[0])
            finally:
                db.close()
            with patch("core.discovery_jira_checkpoint.sources.search_issues",
                       return_value={"issues": [{"key": "APS-2",
                           "fields": {"updated": "2026-10-02T00:00:00Z"}}],
                           "complete": True}) as search:
                updated = discovery_jira_checkpoint.refresh(cfg, ["APS"], path)
            self.assertEqual(updated["coverage"], "complete")
            self.assertIn("updated >=", search.call_args.args[1])
            db = sqlite3.connect(str(path))
            try:
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM jira_raw_issues").fetchone()[0], 2)
                self.assertIsNotNone(db.execute(
                    "SELECT refreshed_at FROM jira_progress").fetchone()[0])
            finally:
                db.close()


    def test_changed_issue_reopens_history_and_comment_checkpoints(self):
        import sqlite3
        cfg = {"jira": {"base_url": "https://jira.example",
                        "email": "x", "api_token": "y"}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "crawl.sqlite"
            original = {"key": "APS-1", "fields": {"updated": "2026-10-01T00:00:00Z"}}
            with patch("core.discovery_jira_checkpoint.sources.send",
                       return_value=Response({"issues": [original]})):
                discovery_jira_checkpoint.crawl(cfg, ["APS"], path)
            db = sqlite3.connect(str(path))
            try:
                db.execute("""CREATE TABLE jira_history_progress
                    (issue_key TEXT PRIMARY KEY, next_start INTEGER, complete INTEGER)""")
                db.execute("""CREATE TABLE jira_comment_progress
                    (issue_key TEXT PRIMARY KEY, next_start INTEGER, complete INTEGER)""")
                db.execute("INSERT INTO jira_history_progress VALUES ('APS-1', 10, 1)")
                db.execute("INSERT INTO jira_comment_progress VALUES ('APS-1', 5, 1)")
                db.commit()
            finally:
                db.close()
            changed = {"key": "APS-1", "fields": {"updated": "2026-10-02T00:00:00Z"}}
            with patch("core.discovery_jira_checkpoint.sources.search_issues",
                       return_value={"issues": [changed], "complete": True}):
                discovery_jira_checkpoint.refresh(cfg, ["APS"], path)
            db = sqlite3.connect(str(path))
            try:
                self.assertEqual(db.execute(
                    "SELECT next_start, complete FROM jira_history_progress").fetchone(), (0, 0))
                self.assertEqual(db.execute(
                    "SELECT next_start, complete FROM jira_comment_progress").fetchone(), (0, 0))
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
