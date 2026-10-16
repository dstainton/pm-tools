"""Regression suite for consolidated offline concept discovery."""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from core import (
    discovery_concepts, discovery_fts, discovery_concept_graph,
    discovery_contextual_candidates, discovery_profile_leads,
)
from core.discovery_identity import IdentityIndex


class ConsolidationTests(unittest.TestCase):
    def test_ambiguous_alias_never_merges_distinct_concepts(self):
        index = IdentityIndex([
            {"project": "APS", "canonical": "Gateway Administrator",
             "aliases": ["GWA"]},
            {"project": "APS", "canonical": "Gateway Administration",
             "aliases": ["GWA"]},
        ])
        self.assertEqual(index.resolve("APS", "GWA"), "GWA")
        self.assertEqual(index.mentions("APS", "GWA depends on SDX"), [])
        self.assertEqual(index.resolve("OTHER", "Gateway Administration"),
                         "Gateway Administration")

    def test_canonical_pairs_and_directed_mapping_are_source_cited(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.sqlite"
            for cid, name, short in (
                    ("sdx", "Secure Data Exchange", "SDX"),
                    ("adr", "Authoritative Data Register", "ADR"),
                    ("efv", "Eligibility Factor Verification", "EFV")):
                discovery_concepts.register(path, cid, name, project="APS")
                discovery_concepts.alias(path, cid, short, "abbreviation",
                                         "jira:APS-seed-" + cid)
            rows = [
                ("1", "jira:APS-4804",
                 "Validate SDX data dictionary mappings against the ADR glossary"),
                ("2", "jira:APS-4805",
                 "Secure Data Exchange (SDX) and Authoritative Data Register (ADR) are documented."),
                ("3", "jira:APS-4806",
                 "The team DID NOT test the SDX onboarding."),
                ("4", "jira:APS-4807",
                 "EFV and SDX technical documentation will be published together."),
            ]
            with closing(sqlite3.connect(str(path))) as db:
                discovery_fts._init(db)
                for key, citation, body in rows:
                    discovery_fts._put(db, key, key, "APS", "issue",
                                       None, None, "", body, citation)
                db.commit()
            queue = discovery_contextual_candidates.candidates(path, project="APS", limit=None)
            mapping = next(item for item in queue if {
                item["from"], item["to"]} == {
                    "Secure Data Exchange", "Authoritative Data Register"})
            self.assertEqual(mapping["strong_sources"], 1)
            self.assertEqual(mapping["evidence"][0]["citation"], "jira:APS-4804")
            self.assertTrue(any(h["type"] == "validated_against" and
                                h["from"] == "Secure Data Exchange" and
                                h["to"] == "Authoritative Data Register"
                                for h in mapping["relationship_hints"]))
            self.assertEqual(len([x for x in queue if {
                x["from"], x["to"]} == {
                "Secure Data Exchange", "Authoritative Data Register"}]), 1)
            graph = discovery_concept_graph.discover(path, project="APS")
            edge = next(e for e in graph["relationships"] if
                        e["type"] == "validated_against")
            self.assertEqual((edge["from"], edge["to"]),
                             ("Secure Data Exchange", "Authoritative Data Register"))
            self.assertEqual(edge["evidence"][0]["citation"], "jira:APS-4804")
            self.assertEqual(edge["status"], "candidate")
            self.assertEqual(graph["indexed_documents"], 4)

    def test_profile_leads_are_not_auto_confirmed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.sqlite"
            with closing(sqlite3.connect(str(path))) as db:
                discovery_fts._init(db)
                discovery_fts._put(
                    db, "1", "1", "APS", "page", None, None,
                    "Secure Data Exchange responsibilities",
                    "Secure Data Exchange provides secure data sharing capabilities.",
                    "confluence:42")
                db.commit()
            cfg = {"products": [{"name": "Connected Services", "abbrev": "CS"}],
                   "workstreams": [{"name": "Secure Data Exchange", "abbrev": "SDX"}]}
            result = discovery_profile_leads.build(path, cfg, project="APS")
            self.assertEqual(result["indexed_documents_scanned"], 1)
            stream = next(e for e in result["entities"] if e["abbrev"] == "SDX")
            self.assertEqual(stream["documents_matched"], 1)
            self.assertEqual(stream["review_state"], "needs human verification")
            self.assertTrue(stream["leads"])
            self.assertFalse(any("confirmed" in key for key in stream))


if __name__ == "__main__":
    unittest.main()
