"""Concept resolution must be scoped, cited, confirmed and offline."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from core import discovery_concepts, discovery_fts


class ConceptTests(unittest.TestCase):
    def test_candidate_not_expanded_but_confirmed_scoped_alias_is(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "evidence.sqlite"
            db = sqlite3.connect(str(path))
            try:
                db.execute("""CREATE TABLE jira_raw_issues (
                    project TEXT, issue_key TEXT, payload TEXT,
                    PRIMARY KEY(project, issue_key))""")
                issue = {"key": "APS-1", "fields": {
                    "summary": "Secure Data Exchange onboarding",
                    "description": "SDX integration"}}
                db.execute("INSERT INTO jira_raw_issues VALUES (?, ?, ?)",
                           ("APS", "APS-1", json.dumps(issue)))
                db.commit()
            finally:
                db.close()
            discovery_fts.index_jira(path)
            discovery_concepts.register(path, "product-one", "APS P2P",
                                        project="APS", status="confirmed")
            discovery_concepts.alias(path, "product-one", "SDX",
                                     "historical_name", "jira:APS-1",
                                     status="candidate")
            self.assertEqual(discovery_concepts.search_concept(path, "APS P2P",
                                                               project="APS"), [])
            discovery_concepts.alias(path, "product-one", "SDX",
                                     "historical_name", "jira:APS-1",
                                     status="confirmed")
            hits = discovery_concepts.search_concept(path, "APS P2P", project="APS")
            self.assertEqual(hits[0]["citation"], "jira:APS-1")
            self.assertEqual(hits[0]["matched_term"], "SDX")
            self.assertEqual(hits[0]["alias_evidence"], "jira:APS-1")
            self.assertEqual(discovery_concepts.search_concept(
                path, "APS P2P", project="OTHER"), [])
            self.assertEqual(discovery_concepts.search_concept(
                path, "APS P2P"), [])


if __name__ == "__main__":
    unittest.main()
