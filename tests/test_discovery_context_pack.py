"""Full-document inference context: scope, breadth, citation fidelity and caps."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from core import (
    discovery_context_pack, discovery_fts, discovery_local_model,
    discovery_profile_model,
)


class RichContextTests(unittest.TestCase):
    def _insert(self, path):
        lead = ("Integration Toolkit provides integration guidance and templates. " * 42)
        middle = ("Architecture and responsibilities are documented in this section. " * 80)
        tail = ("Secure Data Exchange defines the security boundary and policy checks. " * 40)
        confluence_body = lead + middle + tail
        with closing(sqlite3.connect(str(path))) as db:
            discovery_fts._init(db)
            entries = [
                ("confluence-page", "510", "APS", "confluence_page",
                 "Integration Toolkit and Secure Data Exchange architecture",
                 confluence_body, "confluence:510", "confluence"),
                ("jira-issue", "APS-100", "APS", "issue",
                 "Integration Toolkit integration with Secure Data Exchange",
                 "Integration Toolkit depends on Secure Data Exchange for "
                 "policy-scoped tokens. " * 20, "jira:APS-100", "jira"),
                ("jira-comment", "APS-100", "APS", "comment",
                 "Question about Integration Toolkit",
                 "The Secure Data Exchange design was discussed in a meeting.",
                 "jira:APS-100#comment-1", "jira"),
                ("jira-change", "APS-100", "APS", "change",
                 "Integration Toolkit moved",
                 "Changed from Secure Data Exchange to another Jira component.",
                 "jira:APS-100#changelog-1", "jira"),
                ("outside", "777", "OTHER", "confluence_page",
                 "Integration Toolkit and Secure Data Exchange",
                 "OTHER project secrets must never enter APS context.",
                 "confluence:777", "confluence"),
            ]
            for did, key, proj, kind, title, body, cite, source in entries:
                discovery_fts._put(
                    db, did, key, proj, kind, None, None, title, body,
                    cite, source=source)
            db.commit()
        return confluence_body

    def test_full_documents_are_accessible_beyond_previous_500_chars(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.sqlite"
            self._insert(path)
            pack = discovery_context_pack.build(
                path, "APS", ["Integration Toolkit", "Secure Data Exchange"],
                citations=["jira:APS-100"], max_chars=30000, max_documents=8)
            self.assertGreater(pack["characters"], 5000)
            self.assertIn("confluence:510", pack["citations"])
            self.assertIn("jira:APS-100", pack["citations"])
            combined = " ".join(e["excerpt"] for e in pack["evidence"])
            self.assertIn("policy-scoped tokens", combined)
            self.assertIn("defines the security boundary", combined)
            self.assertNotIn("OTHER project secrets", combined)
            self.assertNotIn("Changed from Secure Data Exchange", combined)
            self.assertLessEqual(pack["characters"], 30000)

    def test_context_caps_and_nonadjacent_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.sqlite"
            raw = self._insert(path)
            pack = discovery_context_pack.build(
                path, "APS", ["Integration Toolkit", "Secure Data Exchange"],
                max_chars=6000, max_documents=1)
            self.assertLessEqual(pack["characters"], 6000)
            self.assertEqual(pack["documents"], 1)
            self.assertTrue(pack["truncated"])
            excerpt = pack["evidence"][0]["excerpt"]
            self.assertIn("Integration Toolkit", excerpt)
            self.assertIn("Secure Data Exchange", excerpt)
            self.assertGreater(len(raw), len(excerpt))

    def test_relationship_model_receives_substantially_more_than_one_sentence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.sqlite"
            self._insert(path)
            edge = {"from": "Integration Toolkit", "to": "Secure Data Exchange",
                    "type": "depends_on", "project": "APS",
                    "evidence": [{"citation": "jira:APS-100",
                                  "excerpt": "A short mention."}]}
            answer = json.dumps({
                "type": "depends_on", "citations": ["jira:APS-100"],
                "confidence": "medium", "rationale": "Explicit dependency."})
            with patch("core.model.call_model", return_value=answer) as mocked:
                out = discovery_local_model.review(
                    {"relationships": [edge]}, {"model": {
                        "endpoint": "http://localhost:13305", "name": "test"}},
                    db_path=path, context_chars=30000, context_documents=8)
            payload = json.loads(mocked.call_args.args[2])
            excerpts = payload["evidence"]
            self.assertGreater(sum(len(x["excerpt"]) for x in excerpts), 4000)
            self.assertGreater(out["results"][0]["context_characters"], 4000)
            self.assertIn("confluence:510",
                          out["results"][0]["context_citations"])
            self.assertEqual(out["results"][0]["model"]["type"], "depends_on")

    def test_profile_model_receives_richer_context_with_source_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.sqlite"
            self._insert(path)
            candidate = {"project": "APS", "name": "Integration Toolkit",
                         "evidence": [{"citation": "confluence:510",
                                       "source": "confluence",
                                       "title": "Architecture",
                                       "excerpt": "Short excerpt."}]}
            response = '{"claims":[{"field":"purpose","value":"Provide integration guidance.",' + \
                       '"citations":["confluence:510"]}]}'
            report = {"candidates": [candidate], "total_candidates": 1}
            with patch("core.model.call_model", return_value=response) as mocked:
                output = discovery_profile_model.review(
                    report, {"model": {"endpoint": "http://localhost:13305",
                                      "name": "test"}},
                    db_path=path, context_chars=30000, context_documents=8)
            sent = json.loads(mocked.call_args.args[2])
            self.assertGreater(len(sent["evidence"][0]["excerpt"]), 750)
            self.assertGreater(output["model_review"]["results"][0]["context_characters"], 750)
            self.assertEqual(
                output["model_review"]["results"][0]["result"]["claims"][0]["citations"],
                ["confluence:510"])

    def test_rejects_invalid_budgets(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.sqlite"
            self._insert(path)
            for chars, count in [(3000, 8), (5000, 0), (500000, 8)]:
                with self.subTest(chars=chars, count=count):
                    with self.assertRaises(ValueError):
                        discovery_context_pack.build(
                            path, "APS", ["Integration Toolkit"],
                            max_chars=chars, max_documents=count)


if __name__ == "__main__":
    unittest.main()
