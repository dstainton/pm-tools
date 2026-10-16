"""Typed concept graph tests: citations, scope, and candidate-only decisions."""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from core import discovery_concepts, discovery_fts, discovery_concept_graph


class ConceptGraphTests(unittest.TestCase):
    def test_typed_edges_keep_distinct_sources_and_do_not_confirm(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "terms.sqlite"
            discovery_concepts.register(path, "itk", "Integration Toolkit", project="APS")
            discovery_concepts.alias(path, "itk", "ITK", "abbreviation",
                                     "jira:APS-1")
            with closing(sqlite3.connect(str(path))) as db:
                discovery_fts._init(db)
                for key, scope, citation, body in [
                    ("1", "APS", "jira:APS-2", "ITK depends on SDX."),
                    ("2", "APS", "jira:APS-3", "ITK depends on SDX."),
                    ("3", "OTHER", "jira:OTHER-1", "ITK depends on SDX."),
                ]:
                    discovery_fts._put(db, key, key, scope, "issue", None,
                                       None, "", body, citation)
                db.commit()
            result = discovery_concept_graph.discover(path, project="APS")
            self.assertEqual(result["identity_total"], 1)
            edge = next(e for e in result["relationships"] if e["type"] == "depends_on")
            self.assertEqual((edge["from"], edge["to"]), ("Integration Toolkit", "SDX"))
            self.assertEqual(edge["independent_sources"], 2)
            self.assertEqual(edge["status"], "candidate")
            self.assertEqual({x["citation"] for x in edge["evidence"]},
                             {"jira:APS-2", "jira:APS-3"})

    def test_plain_mention_is_not_typed_edge(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "terms.sqlite"
            with closing(sqlite3.connect(str(path))) as db:
                discovery_fts._init(db)
                discovery_fts._put(db, "1", "1", "APS", "issue",
                                   None, None, "", "ITK and SDX coordinate work.",
                                   "jira:APS-2")
                db.commit()
            result = discovery_concept_graph.discover(path, project="APS")
            self.assertEqual(result["relationship_total"], 0)


if __name__ == "__main__":
    unittest.main()
