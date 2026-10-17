"""Regression coverage for the quality failures in the first APS profile run."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from core import discovery_fts, discovery_context_pack
from core import discovery_profile_discovery as discovery
from core import discovery_profile_model as profile_model


class CandidateQualityTests(unittest.TestCase):
    def test_flattened_capability_headings_exclude_service_field_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_file = Path(tmp) / "index.db"
            with closing(sqlite3.connect(str(db_file))) as db:
                discovery_fts._init(db)
                db.execute("""CREATE TABLE jira_raw_issues
                    (project TEXT, issue_key TEXT, payload TEXT)""")
                for number in range(4):
                    db.execute("INSERT INTO jira_raw_issues VALUES (?,?,?)",
                               ("APS", "APS-" + str(number),
                                json.dumps({"fields":{"components":[
                                    {"name":"user"},{"name":"research"},
                                    {"name":"Integration Toolkit"}]}})))
                description = (
                    "Capability 1: API Gateway Service Owner APS "
                    "What it IS A managed proxy for published services. "
                    "What it is NOT It is not the upstream service. "
                    "Gateway Service: represents the upstream service or API. "
                    "Service: https://example.invalid "
                    "Capability 2: API Directory Owner APS "
                    "What it IS A catalogue to discover and request access to APIs. "
                    "Capability 4: Integration Toolkit (ITK) Owner APS "
                    "What it IS Guidance for developers.")
                discovery_fts._put(
                    db, "confluence:500", "500", "APS", "confluence_page",
                    None, None, "APS capability cards", description,
                    "confluence:500", source="confluence")
                db.commit()
            result = discovery.discover(
                db_file, {"workstreams":[{"name":"Integration Toolkit"}]},
                "APS", max_candidates=40)
            names = {c["name"]: c for c in result["candidates"]}
            self.assertIn("API Gateway Service", names)
            self.assertIn("API Directory", names)
            self.assertIn("Integration Toolkit", names)
            for false in ("user", "research", "https",
                          "represents the upstream service or API"):
                self.assertNotIn(false, names)
            self.assertGreater(result["component_leads_count"], 0)
            self.assertIn("user", {x["name"] for x in result["component_leads"]})

    def test_retrieval_isolates_named_capability_card_and_prioritizes_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_file = Path(tmp) / "index.db"
            with closing(sqlite3.connect(str(db_file))) as db:
                discovery_fts._init(db)
                intro = "Integration Toolkit planning agenda; review implementation details. " * 70
                cards = (
                    "Capability 1: API Gateway Service Owner APS What it IS "
                    "A proxy for upstream APIs. What it is NOT An API host. "
                    "Capability 4: Integration Toolkit Owner APS What it IS "
                    "A developer onboarding resource and discoverability support. "
                    "What it is NOT Not a data exchange gateway. "
                    "Capability 5: Secure Data Exchange Owner APS What it IS "
                    "An exchange protocol with policy enforcement.")
                discovery_fts._put(
                    db, "confluence:501", "501", "APS", "confluence_page",
                    None, None, "Planning", intro,
                    "confluence:501", source="confluence")
                discovery_fts._put(
                    db, "confluence:502", "502", "APS", "confluence_page",
                    None, None, "Capability catalogue", cards,
                    "confluence:502", source="confluence")
                db.commit()
            pack = discovery_context_pack.build(
                db_file, "APS", ["Integration Toolkit"],
                citations=["confluence:501"],
                max_chars=10000, max_documents=3, profile=True)
            self.assertEqual(pack["evidence"][0]["citation"], "confluence:502")
            text = pack["evidence"][0]["excerpt"]
            self.assertIn("developer onboarding resource", text)
            self.assertIn("Not a data exchange gateway", text)
            self.assertNotIn("Capability 1:", text)
            self.assertNotIn("Capability 5:", text)


class MultiPassInferenceTests(unittest.TestCase):
    def setUp(self):
        self.candidate = {"name":"Integration Toolkit", "project":"APS"}

    def test_multi_pass_merges_valid_claims_from_distinct_sources(self):
        context = {"evidence":[
            {"citation":"confluence:100", "source":"confluence", "kind":"confluence_page",
             "title":"ITK", "excerpt":"Integration Toolkit provides onboarding. " * 180},
            {"citation":"confluence:101", "source":"confluence", "kind":"confluence_page",
             "title":"ITK Scope", "excerpt":"Integration Toolkit does not host APIs. " * 180}
        ]}
        outputs = [
            '{"claims":[{"field":"responsibility","value":"Provide onboarding.",'
            '"citations":["confluence:100"]}]}',
            '{"claims":[{"field":"boundary","value":"Does not host APIs.",'
            '"citations":["confluence:101"]}]}'
        ]
        with patch("core.model.call_model", side_effect=outputs) as mock:
            result = profile_model._merge_passes(
                self.candidate, {"json_temperature":0.2}, context)
        self.assertEqual(result["status"], "unconfirmed_model_proposal")
        self.assertEqual(result["passes"], 2)
        self.assertEqual(mock.call_count, 2)
        self.assertEqual({claim["field"] for claim in result["claims"]},
                         {"boundary", "responsibility"})

    def test_empty_success_is_distinguished_from_usable_result(self):
        context = {"evidence":[
            {"citation":"confluence:100", "source":"confluence", "kind":"confluence_page",
             "title":"ITK", "excerpt":"An incomplete document."}
        ]}
        with patch("core.model.call_model", return_value='{"claims":[]}'):
            result = profile_model._merge_passes(
                self.candidate, {"json_temperature":0.2}, context)
        self.assertEqual(result["status"], "no_supported_claims")
        self.assertEqual(result["empty_passes"], 1)
        self.assertEqual(result["claims"], [])


if __name__ == "__main__":
    unittest.main()
