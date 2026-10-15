"""Evidence alias candidates remain unconfirmed and project-scoped."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from core import discovery_alias_candidates, discovery_concepts


class AliasMiningTests(unittest.TestCase):
    def test_mines_explicit_acronym_and_stages_as_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.sqlite"
            db = sqlite3.connect(str(path))
            try:
                db.execute("""CREATE TABLE discovery_fts_documents (
                    citation TEXT, project TEXT, title TEXT, body TEXT, kind TEXT)""")
                db.executemany("INSERT INTO discovery_fts_documents VALUES (?, ?, ?, ?, ?)", [
                    ("jira:APS-1", "APS", "Secure Data Exchange (SDX)", "", "issue"),
                    ("jira:APS-2", "APS", "Intro", "Secure Data Exchange (SDX) onboarding", "comment"),
                    ("jira:OTHER-1", "OTHER", "Secure Data Exchange (SDX)", "", "issue"),
                    ("jira:APS-3", "APS", "Application Programming Interface (API) architecture", "", "issue"),
                ])
                db.commit()
            finally:
                db.close()
            entries = discovery_alias_candidates.candidates(path, project="APS")
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[1]["canonical"], "Application Programming Interface")
            self.assertEqual(entries[1]["alignment"], "schwartz-hearst")
            self.assertEqual(entries[0]["canonical"], "Secure Data Exchange")
            self.assertEqual(len(entries[0]["citations"]), 2)
            self.assertEqual(entries[0]["alignment"], "schwartz-hearst")
            staged = discovery_alias_candidates.stage(path, project="APS")
            self.assertEqual(len(staged), 2)
            db = sqlite3.connect(str(path))
            try:
                self.assertEqual(db.execute(
                    "SELECT DISTINCT status FROM discovery_aliases").fetchone()[0], "candidate")
                self.assertEqual(db.execute(
                    "SELECT status FROM discovery_concepts").fetchone()[0], "candidate")
            finally:
                db.close()
            self.assertEqual(discovery_concepts.expansions(
                path, "Secure Data Exchange", project="APS"), [])


if __name__ == "__main__":
    unittest.main()
