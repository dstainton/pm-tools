"""Opt-in offline candidate product/workstream discovery never edits source data."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from core import discovery_fts, discovery_profile_discovery as profiles
from core import discovery_profile_model as model_profiles


class ProfileDiscoveryTests(unittest.TestCase):
    def _db(self, path):
        with closing(sqlite3.connect(str(path))) as db:
            discovery_fts._init(db)
            db.execute("""CREATE TABLE jira_raw_issues (
                project TEXT NOT NULL, issue_key TEXT NOT NULL,
                payload TEXT NOT NULL, PRIMARY KEY(project, issue_key))""")
            for project, key, comps in [
                ("APS", "APS-100", ["Integration Toolkit", "API Services Gateway"]),
                ("APS", "APS-101", ["Integration Toolkit", "API Services Gateway"]),
                ("APS", "APS-102", ["Secure Data Exchange"]),
                ("APS", "APS-103", ["Secure Data Exchange"]),
                ("OTHER", "OTHER-1", ["Unrelated Project"]),
            ]:
                db.execute("INSERT INTO jira_raw_issues VALUES(?,?,?)", (
                    project, key, json.dumps({"fields": {
                        "components": [{"name": c} for c in comps]}})))
            def index(doc_id, project, source_key, kind, title, body, citation,
                      source="confluence"):
                discovery_fts._put(db, doc_id, source_key, project, kind,
                                   None, None, title, body, citation,
                                   source=source)
            index("page-1", "APS", "510", "confluence_page",
                  "APS capabilities",
                  "Capability 4: Integration Toolkit (ITK) Owner: APS. "
                  "Integration Toolkit provides API documentation and onboarding. "
                  "Product: Secure Data Exchange High-Level Objective: "
                  "Secure Data Exchange enables trusted cross-boundary exchange.",
                  "confluence:510")
            index("page-2", "APS", "511", "confluence_page",
                  "API Services Gateway",
                  "Workstream: API Services Gateway Owner: APS. "
                  "API Services Gateway provides API publishing.",
                  "confluence:511")
            index("issue1", "APS", "APS-100", "issue",
                  "Integration Toolkit onboarding",
                  "Integration Toolkit supports API developer onboarding.",
                  "jira:APS-100", source="jira")
            index("issue2", "APS", "APS-101", "issue",
                  "Integration Toolkit discovery",
                  "Integration Toolkit provides documentation and search.",
                  "jira:APS-101", source="jira")
            index("issue3", "APS", "APS-102", "issue",
                  "Secure Data Exchange connection",
                  "Secure Data Exchange provides secure message transmission.",
                  "jira:APS-102", source="jira")
            index("issue4", "APS", "APS-103", "issue",
                  "Secure Data Exchange tokens",
                  "Secure Data Exchange provides tokens.",
                  "jira:APS-103", source="jira")
            for k in range(15):
                index("comment-" + str(k), "APS", "APS-100", "comment",
                      "Integration Toolkit discussion",
                      "Integration Toolkit deployment concern.",
                      "jira:APS-100#comment-" + str(k), source="jira")
                index("change-" + str(k), "APS", "APS-100", "change",
                      "Integration Toolkit history",
                      "Integration Toolkit was moved in Jira.",
                      "jira:APS-100#changelog-" + str(k), source="jira")
            index("unrelated", "OTHER", "OTHER-1", "confluence_page",
                  "Unrelated Project", "Product: Unrelated Project",
                  "confluence:999")
            db.commit()

    def test_independent_names_source_evidence_and_reconciliation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "index.sqlite"
            self._db(path)
            cfg = {
                "products": [{"name": "Integration Toolkit"}],
                "workstreams": [{"name": "Secure Data Exchange"}]}
            result = profiles.discover(path, cfg, "APS")
            names = {c["name"]: c for c in result["candidates"]}
            self.assertIn("Integration Toolkit", names)
            self.assertIn("Secure Data Exchange", names)
            self.assertIn("API Services Gateway", names)
            self.assertNotIn("Unrelated Project", names)
            itk = names["Integration Toolkit"]
            self.assertEqual(itk["component_issue_count"], 2)
            self.assertEqual(itk["jira_issues"], 2)
            self.assertEqual(itk["published_documents"], 1)
            self.assertEqual(itk["reconciliation"]["status"], "kind_conflict")
            self.assertIn("capability", itk["observed_labels"])
            self.assertEqual(len(itk["evidence"]), 3)
            self.assertEqual(itk["evidence"][0]["citation"], "confluence:510")
            self.assertEqual(names["API Services Gateway"]["candidate_kind"],
                             "workstream")
            self.assertEqual(names["API Services Gateway"]["reconciliation"]["status"],
                             "not_configured")
            self.assertTrue(result["config_unchanged"])

    def test_profile_cap_and_missing_project(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "index.sqlite"
            self._db(path)
            results = profiles.discover(path, {}, "APS", max_candidates=1)
            self.assertEqual(len(results["candidates"]), 1)
            self.assertEqual(results["unreviewed_candidates"],
                             results["total_candidates"] - 1)
            with self.assertRaises(ValueError):
                profiles.discover(path, {}, None)

    def test_no_unpublished_and_activity_evidence_in_primary_claims(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "index.sqlite"
            self._db(path)
            result = profiles.discover(path, {}, "APS")
            text = " ".join(str(e) for x in result["candidates"]
                            for e in x["evidence"])
            self.assertNotIn("comment-", text)
            self.assertNotIn("changelog-", text)
            self.assertNotIn("Unrelated Project", text)


class ProfileModelTests(unittest.TestCase):
    def setUp(self):
        self.candidate = {
            "project": "APS", "name": "Integration Toolkit",
            "evidence": [{
                "citation": "confluence:510", "title": "Capabilities",
                "source": "confluence", "excerpt":
                    "Integration Toolkit provides API onboarding."}]}
        self.cfg = {"endpoint": "http://localhost:1234", "name": "local"}

    def test_one_cited_claim_and_strict_json(self):
        raw = json.dumps({"claims": [{
            "field": "responsibility", "value": "Provide API onboarding.",
            "citations": ["confluence:510"]}]})
        with patch("core.model.call_model", return_value=raw) as mocked:
            result = model_profiles.extract(self.candidate, self.cfg)
        self.assertEqual(result["status"], "unconfirmed_model_proposal")
        self.assertFalse(result["repair_attempted"])
        self.assertEqual(result["claims"][0]["field"], "responsibility")
        self.assertEqual(mocked.call_count, 1)

    def test_repair_malformed_json_on_second_turn(self):
        repaired = '{"claims":[{"field":"purpose","value":"Support API publishing.",' + \
                   '"citations":["confluence:510"]}]}'
        with patch("core.model.call_model", side_effect=[
                '{"claims":', repaired]) as mocked:
            result = model_profiles.extract(self.candidate, self.cfg)
        self.assertTrue(result["repair_attempted"])
        self.assertEqual(len(result["claims"]), 1)
        self.assertEqual(mocked.call_count, 2)

    def test_invalid_citation_and_unknown_kind_rejected(self):
        for value in [
            '{"claims":[{"field":"parent","value":"APS","citations":["invented"]}]}',
            '{"claims":[{"field":"kind","value":"corporation",'
            '"citations":["confluence:510"]}]}',
            '{"claims":[{"field":"purpose","value":"No cite","citations":[]}]}',
        ]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    model_profiles._validate(value, {"confluence:510"})

    def test_failed_repair_cannot_become_a_claim(self):
        with patch("core.model.call_model", side_effect=[
                '{"claims":', '{"claims":[]} garbage']) as mocked:
            result = model_profiles.extract(self.candidate, self.cfg)
        self.assertEqual(result["status"], "model_error")
        self.assertEqual(result["claims"], [])
        self.assertEqual(mocked.call_count, 2)

    def test_model_review_bounded(self):
        report = {"total_candidates": 5, "candidates": [self.candidate] * 3}
        with patch.object(model_profiles, "extract", return_value={
                "status": "unconfirmed_model_proposal", "claims": []}) as call:
            model_profiles.review(report, {"model": self.cfg}, max_candidates=2)
        self.assertEqual(call.call_count, 2)
        self.assertEqual(report["model_review"]["remaining"], 3)


if __name__ == "__main__":
    unittest.main()
