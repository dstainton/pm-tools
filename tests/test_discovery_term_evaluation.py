"""Evidence-pair evaluation is conservative, scoped and source-cited."""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from core import discovery_fts, discovery_term_evaluation


class TermEvaluationTests(unittest.TestCase):
    def test_explicit_pair_with_contradiction_remains_unconfirmed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.sqlite"
            with closing(sqlite3.connect(str(path))) as db:
                discovery_fts._init(db)
                samples = [
                    ("j", "APS", "jira:APS-10",
                     "APS P2P (formerly SDX) is a service."),
                    ("c", "APS", "confluence:11",
                     "APS P2P and SDX are separate in this architecture."),
                    ("u", "OTHER", "jira:OTHER-1",
                     "APS P2P (formerly SDX) is irrelevant elsewhere."),
                ]
                for key, project, citation, body in samples:
                    discovery_fts._put(db, key, key, project, "issue",
                                       None, None, "Example", body, citation)
                db.commit()
            result = discovery_term_evaluation.evaluate(path, project="APS")
            match = next(x for x in result["evaluations"]
                         if {x["a"], x["b"]} == {"APS P2P", "SDX"})
            self.assertEqual(match["assessment"], "conflicting_evidence")
            self.assertEqual(match["status"], "candidate")
            self.assertEqual({e["citation"] for e in match["evidence"]},
                             {"jira:APS-10", "confluence:11"})

    def test_cooccurrence_does_not_become_equivalence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.sqlite"
            with closing(sqlite3.connect(str(path))) as db:
                discovery_fts._init(db)
                discovery_fts._put(db, "d", "d", "APS", "issue",
                                   None, None, "", "APS P2P and SDX appeared together.",
                                   "jira:APS-2")
                db.commit()
            pair = {"project": "APS", "a": "APS P2P", "b": "SDX",
                    "basis": ["candidate"], "source_citations": []}
            with patch.object(discovery_term_evaluation, "generate",
                              return_value=[pair]):
                result = discovery_term_evaluation.evaluate(path, project="APS")
            self.assertEqual(result["evaluations"][0]["assessment"], "unresolved")
            self.assertEqual(result["evaluations"][0]["evidence_count"], 1)


if __name__ == "__main__":
    unittest.main()
