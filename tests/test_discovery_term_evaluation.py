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

    def test_contextual_pair_has_independent_source_dossier(self):
        from core import discovery_concepts
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.sqlite"
            discovery_concepts.register(path, "sdx", "Secure Data Exchange", project="APS")
            discovery_concepts.alias(path, "sdx", "SDX", "abbreviation",
                                     "jira:APS-1")
            with closing(sqlite3.connect(str(path))) as db:
                discovery_fts._init(db)
                samples = [
                    ("jira:APS-10", "SDX and APS P2P integration planning", "2025-01-01"),
                    ("jira:APS-11", "APS P2P work follows SDX discovery", "2026-01-01"),
                    ("jira:APS-12", "SDX and APS P2P review the same dependencies", "2026-02-01"),
                ]
                for idx, (citation, body, when) in enumerate(samples):
                    discovery_fts._put(db, "doc" + str(idx), "key", "APS", "issue",
                                       when, when, "", body, citation)
                db.commit()
            pairs = discovery_term_evaluation.generate(path, project="APS")
            self.assertTrue(any({p["a"], p["b"]} == {"SDX", "APS P2P"}
                                for p in pairs))
            result = discovery_term_evaluation.evaluate(path, project="APS")
            match = next(p for p in result["evaluations"]
                         if {p["a"], p["b"]} == {"SDX", "APS P2P"})
            self.assertEqual(match["assessment"], "unresolved")
            self.assertEqual(match["independent_sources"], 3)
            self.assertEqual(len({e["citation"] for e in match["evidence"]}), 3)

    def test_generic_distinction_elsewhere_does_not_disprove_pair(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.sqlite"
            with closing(sqlite3.connect(str(path))) as db:
                discovery_fts._init(db)
                discovery_fts._put(
                    db, "d", "d", "APS", "issue", None, None, "",
                    "APS and SDX integration. Different environments require "
                    "different API keys.", "jira:APS-8")
                db.commit()
            pair = {"project": "APS", "a": "APS", "b": "SDX",
                    "basis": ["candidate"], "source_citations": []}
            with patch.object(discovery_term_evaluation, "generate",
                              return_value=[pair]):
                result = discovery_term_evaluation.evaluate(path, project="APS")
            self.assertEqual(result["evaluations"][0]["assessment"], "unresolved")

    def test_distant_codes_do_not_generate_contextual_pairs(self):
        from core import discovery_concepts
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.sqlite"
            discovery_concepts.register(path, "c", "Secure Data Exchange",
                                        project="APS")
            discovery_concepts.alias(path, "c", "SDX", "abbreviation",
                                     "jira:APS-1")
            with closing(sqlite3.connect(str(path))) as db:
                discovery_fts._init(db)
                for i in range(3):
                    body = "SDX gateway deployment. " + ("unrelated prose. " * 25) + "OWASP compliance."
                    discovery_fts._put(db, str(i), str(i), "APS", "issue",
                                       None, None, "", body, "jira:APS-" + str(i))
                db.commit()
            self.assertFalse(any(
                {p["a"], p["b"]} == {"SDX", "OWASP"}
                for p in discovery_term_evaluation.generate(path, project="APS")))

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
