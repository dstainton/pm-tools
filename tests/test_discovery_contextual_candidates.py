"""Grounded contextual pairs stay hypotheses until source review."""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from core import discovery_concepts, discovery_contextual_candidates, discovery_fts


class ContextualCandidatesTests(unittest.TestCase):
    def test_same_identity_names_do_not_become_contextual_relationships(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "docs.sqlite"
            discovery_concepts.register(path, "sdx", "Secure Data Exchange",
                                        project="APS")
            discovery_concepts.alias(path, "sdx", "SDX", "abbreviation",
                                     "jira:APS-seed")
            with closing(sqlite3.connect(str(path))) as db:
                discovery_fts._init(db)
                for i in range(3):
                    discovery_fts._put(
                        db, str(i), str(i), "APS", "issue", None, None,
                        "", "Secure Data Exchange (SDX) documentation.",
                        "jira:APS-" + str(i))
                db.commit()
            self.assertFalse(discovery_contextual_candidates.candidates(
                path, project="APS"))

    def test_pairs_from_narrative_are_cited_not_typed(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "docs.sqlite"
            for key, title, short in [
                ("itk", "Integration Toolkit", "ITK"),
                ("sdx", "Secure Data Exchange", "SDX"),
            ]:
                discovery_concepts.register(path, key, title, project="APS")
                discovery_concepts.alias(path, key, short, "abbreviation",
                                         "jira:APS-seed-" + key)
            with closing(sqlite3.connect(str(path))) as db:
                discovery_fts._init(db)
                for i, body in enumerate([
                    "ITK provides a catalogue of SDX service documentation.",
                    "SDX documentation will appear within ITK experiences.",
                ]):
                    discovery_fts._put(db, str(i), str(i), "APS", "issue",
                                       None, None, "", body, "jira:APS-" + str(i))
                discovery_fts._put(db, "other", "other", "OTHER", "issue",
                                   None, None, "", "ITK and SDX share names.",
                                   "jira:OTHER-1")
                db.commit()
            result = discovery_contextual_candidates.candidates(path, project="APS")
            match = [x for x in result if {x["from"], x["to"]} == {"ITK", "SDX"}]
            self.assertEqual(len(match), 1)
            self.assertEqual(match[0]["type"], "unresolved")
            self.assertEqual(match[0]["status"], "candidate")
            self.assertEqual({e["citation"] for e in match[0]["evidence"]},
                             {"jira:APS-0", "jira:APS-1"})


if __name__ == "__main__":
    unittest.main()
