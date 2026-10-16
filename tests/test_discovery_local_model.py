"""Concept graph model uses the configured inference stack."""
import json
import unittest
from unittest.mock import patch

from core import discovery_local_model, model


class LocalModelTests(unittest.TestCase):
    def setUp(self):
        self.edge = {"from": "ITK", "to": "SDX", "type": "depends_on",
                     "project": "APS", "evidence": [
                         {"citation": "jira:APS-1", "kind": "issue",
                          "excerpt": "ITK depends on SDX."}]}
        self.cfg = {"model": {"endpoint": "http://127.0.0.1:13305/api/v1/chat/completions",
                              "name": "local-qwen", "json_temperature": 0.2}}

    def test_grounded_proposal_uses_shared_model_client(self):
        answer = {"type": "depends_on", "citations": ["jira:APS-1"],
                  "confidence": "medium", "rationale": "An explicit dependency."}
        with patch.object(model, "call_model", return_value=json.dumps(answer)) as mocked:
            result = discovery_local_model.classify(self.edge, self.cfg["model"])
        self.assertEqual(result["status"], "unconfirmed_model_proposal")
        self.assertEqual(result["citations"], ["jira:APS-1"])
        self.assertIs(mocked.call_args.args[0], self.cfg["model"])

    def test_rejects_unseen_citations(self):
        answer = {"type": "depends_on", "citations": ["jira:APS-999"],
                  "confidence": "high", "rationale": "Invented reference."}
        with patch.object(model, "call_model", return_value=json.dumps(answer)):
            with self.assertRaises(ValueError):
                discovery_local_model.classify(self.edge, self.cfg["model"])

    def test_review_reuses_existing_model_settings(self):
        with patch.object(discovery_local_model, "classify",
                          return_value={"status": "no_evidence", "type": "unresolved",
                                        "citations": []}) as mocked:
            result = discovery_local_model.review(
                {"relationships": [self.edge]}, self.cfg)
        self.assertEqual(result["model_name"], "local-qwen")
        self.assertIs(mocked.call_args.args[1], self.cfg["model"])

    def test_review_errors_are_not_confirmations(self):
        graph = {"relationships": [self.edge]}
        with patch.object(discovery_local_model, "classify",
                          side_effect=ValueError("Bad JSON")):
            result = discovery_local_model.review(graph, self.cfg)
        self.assertEqual(result["results"][0]["model"]["status"], "model_error")
        self.assertEqual(result["results"][0]["model"]["type"], "unresolved")


if __name__ == "__main__":
    unittest.main()
