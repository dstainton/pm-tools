"""Reference sampling only; these are not human-reviewed annotations."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from core import discovery_benchmark_select as sample
from core import discovery_fts


class PrivateSelectionTests(unittest.TestCase):
    def _data(self, path):
        db = sqlite3.connect(str(path))
        discovery_fts._init(db)
        db.execute(
            "CREATE TABLE jira_raw_issues (project TEXT, issue_key TEXT, payload TEXT)")
        db.execute("INSERT INTO jira_raw_issues VALUES(?,?,?)", (
            "APS", "APS-100", json.dumps({
                "fields": {"labels": ["identity", "architecture"]}})))
        rows = [
            ("page-1", "510", "APS", "confluence_page",
             "APS capability cards",
             "Capability 1: API Gateway Service What it IS "
             "A managed proxy that controls upstream access. " * 8,
             "confluence:510", "confluence"),
            ("page-2", "511", "APS", "confluence_page",
             "Architecture decision", "Decision: Secure Data Exchange depends on "
             "a token exchange service. The decision was superseded. " * 7,
             "confluence:511", "confluence"),
            ("page-3", "512", "APS", "confluence_page",
             "Integration Toolkit", "Integration Toolkit supports API discovery "
             "and developer guidance. " * 8,
             "confluence:512", "confluence"),
            ("jira-1", "APS-100", "APS", "issue",
             "Token exchange dependency",
             "Secure Data Exchange depends on SSO token exchange. " * 8,
             "jira:APS-100", "jira"),
            ("other", "OTHER-1", "OTHER", "confluence_page",
             "Architecture decision", "SECRET CROSS PROJECT CONTENT " * 20,
             "confluence:999", "confluence"),
            ("change", "APS-100", "APS", "change",
             "Secure Data Exchange", "Fake historical change " * 30,
             "jira:APS-100#changelog-1", "jira"),
        ]
        for did, key, project, kind, title, body, cite, source in rows:
            discovery_fts._put(db, did, key, project, kind,
                               None, None, title, body, cite, source=source)
        db.commit()
        db.close()

    def test_project_scope_and_source_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.sqlite"
            self._data(path)
            report = sample.select(path, "APS", 26)
            self.assertEqual(report["review_status"], "NOT_GROUND_TRUTH")
            citations = [x["source"]["citation"] for x in report["cases"]]
            self.assertEqual(len(citations), len(set(citations)))
            self.assertNotIn("confluence:999", citations)
            self.assertNotIn("jira:APS-100#changelog-1", citations)
            self.assertIn("confluence:510", citations)
            self.assertTrue(all(x["illustrative_only"] for x in report["cases"]))
            self.assertTrue(all(x["review_status"] == "pending_human_annotation"
                                for x in report["cases"]))
            for row in report["cases"]:
                source = row["source"]
                self.assertEqual(source["quote"], self._body_slice(
                    path, source["citation"], source["start"], source["end"]))

    @staticmethod
    def _body_slice(path, citation, start, end):
        db = sqlite3.connect(str(path))
        try:
            body = db.execute(
                "SELECT body FROM discovery_fts_documents WHERE citation=?", (citation,)
            ).fetchone()[0]
            return body[start:end]
        finally:
            db.close()

    def test_jira_labels_are_retained_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.sqlite"
            self._data(path)
            report = sample.select(path, "APS", 26)
            jira = next(x for x in report["cases"]
                        if x["source"]["citation"] == "jira:APS-100")
            self.assertEqual(jira["source"]["jira_labels"],
                             ["architecture", "identity"])
            self.assertEqual(jira["source"]["label_status"], "available")
            conf = next(x for x in report["cases"]
                        if x["source"]["citation"] == "confluence:510")
            self.assertEqual(conf["source"]["label_status"], "not_indexed")

    def test_small_corpus_reports_shortfall_without_invented_examples(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.sqlite"
            self._data(path)
            report = sample.select(path, "APS", 26)
            self.assertLess(report["selected"], report["requested"])
            self.assertEqual(report["selected"], len(report["cases"]))

    def test_balanced_sources_despite_many_confluence_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.sqlite"
            self._data(path)
            db = sqlite3.connect(str(path))
            for n in range(20):
                discovery_fts._put(
                    db, "extra:{}".format(n), str(2000 + n), "APS",
                    "confluence_page", None, None,
                    "Secure Data Exchange reference {}".format(n),
                    ("Secure Data Exchange provides secure capability "
                     "and depends on token exchange. ") * 12,
                    "confluence:{}".format(2000 + n),
                    source="confluence")
            for n in range(12):
                issue_key = "APS-{}".format(3000 + n)
                discovery_fts._put(
                    db, "jira:issue:" + issue_key, issue_key, "APS",
                    "issue", None, None, "Integration Toolkit dependency",
                    ("Integration Toolkit provides a service and depends on "
                     "API Directory and APS Platform. ") * 10,
                    "jira:" + issue_key, source="jira")
            db.commit()
            db.close()
            report = sample.select(path, "APS", 26)
            self.assertGreaterEqual(report["source_counts"]["jira"], 8)
            self.assertGreaterEqual(report["source_counts"]["confluence"], 12)
            self.assertEqual(report["selected"],
                             sum(report["source_counts"].values()))

    def test_invalid_limit(self):
        with self.assertRaisesRegex(ValueError, "target"):
            sample.select("unused.sqlite", "APS", 2)


if __name__ == "__main__":
    unittest.main()
