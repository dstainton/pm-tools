"""Explicit contextual relationships require citations and remain proposals."""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from core import discovery_fts, discovery_term_relationships


class ContextualTermRelationshipTests(unittest.TestCase):
    def test_explicit_change_across_sources_and_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.sqlite"
            with closing(sqlite3.connect(str(path))) as db:
                discovery_fts._init(db)
                examples = [
                    ("j1", "APS", "jira:APS-19",
                     "APS P2P (formerly SDX) supports cross-boundary exchange"),
                    ("c1", "APS", "confluence:95",
                     "APS P2P (formerly SDX) handles authorization"),
                    ("j2", "APS", "jira:APS-21",
                     "Secure Data Exchange and APS P2P discussed together."),
                    ("j3", "OTHER", "jira:OTHER-2",
                     "Other Tool (formerly SDX) unrelated"),
                ]
                for doc_id, project, citation, body in examples:
                    discovery_fts._put(db, doc_id, doc_id, project, "issue", None,
                                       None, "", body, citation)
                db.commit()
            result = discovery_term_relationships.propose(path, project="APS")
            candidates = result["relationships"]
            match = next(x for x in candidates if x["from"] == "APS P2P")
            self.assertEqual(match["to"], "SDX")
            self.assertEqual(match["relationship"], "historical_name")
            self.assertEqual(match["status"], "candidate")
            self.assertEqual(match["evidence_count"], 2)
            self.assertEqual({e["citation"] for e in match["evidence"]},
                             {"jira:APS-19", "confluence:95"})
            self.assertEqual(result["examined_documents"], 3)
            self.assertEqual(len(candidates), 1)

    def test_real_world_false_positives_are_rejected(self):
        false_examples = [
            "And how GatewayConfig replaces what is there, whereas other resources will patch.",
            "Aubrey noted the final list may be captured somewhere in the ITSM (formerly ITSM Demo) space.",
            "Root cause of issues during failover: pipeline fails which revealed dependency issue between Portal and Keycloak (previously hidden from maintenance turning off).",
            "This replaces the current use of username for that value.",
            "The site replaces the api.gov.bc.ca url.",
            "The warning says which replaces Docker with a composite action.",
        ]
        for sentence in false_examples:
            with self.subTest(sentence=sentence):
                self.assertEqual(list(discovery_term_relationships._matches(sentence)), [])

    def test_real_world_named_entities_are_retained(self):
        self.assertIn(("historical_name", "OrgBook", "BC Online"),
                      list(discovery_term_relationships._matches(
                          "CITZ - BC Registries, OrgBook (formerly BC Online)")))
        self.assertIn(("historical_name", "APS P2P", "SDX"),
                      list(discovery_term_relationships._matches(
                          "APS P2P (formerly SDX) supports exchange")))

    def test_no_equality_from_cooccurrence_and_no_auto_confirm(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.sqlite"
            with closing(sqlite3.connect(str(path))) as db:
                discovery_fts._init(db)
                discovery_fts._put(db, "d1", "d1", "APS", "issue", None, None,
                                   "", "SDX is often discussed near APS P2P.",
                                   "jira:APS-2")
                db.commit()
            result = discovery_term_relationships.propose(path, project="APS")
            self.assertEqual(result["relationships"], [])


if __name__ == "__main__":
    unittest.main()
