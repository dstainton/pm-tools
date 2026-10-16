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

    def test_citation_outside_submitted_evidence_is_rejected(self):
        edge = dict(self.edge, evidence=[
            {"citation": "jira:APS-" + str(i), "excerpt": "Relevant passage."}
            for i in range(10)])
        answer = {"type": "related_to", "citations": ["jira:APS-9"],
                  "confidence": "medium", "rationale": "Unsupported selection."}
        with patch.object(model, "call_model", return_value=json.dumps(answer)):
            with self.assertRaisesRegex(ValueError, "eight supplied"):
                discovery_local_model.classify(edge, self.cfg["model"])

    def test_invalid_json_gets_one_repair_turn(self):
        valid = {"type": "depends_on", "citations": ["jira:APS-1"],
                 "rationale": "Explicit dependency.", "confidence": "medium"}
        with patch.object(model, "call_model", side_effect=[
                '{"type": depends_on}', json.dumps(valid)]) as mocked:
            result = discovery_local_model.classify(self.edge, self.cfg["model"])
        self.assertTrue(result["repair_attempted"])
        self.assertEqual(result["type"], "depends_on")
        self.assertEqual(mocked.call_count, 2)
        self.assertFalse(mocked.call_args.kwargs["use_cache"])

    def test_ungrounded_repair_still_fails(self):
        bad = {"type": "depends_on", "citations": ["jira:APS-99"],
               "rationale": "Invented.", "confidence": "high"}
        with patch.object(model, "call_model", side_effect=[
                json.dumps(bad), json.dumps(bad)]) as mocked:
            with self.assertRaisesRegex(ValueError, "repair failed"):
                discovery_local_model.classify(self.edge, self.cfg["model"])
        self.assertEqual(mocked.call_count, 2)

    def test_valid_response_does_not_trigger_repair(self):
        good = {"type": "unresolved", "citations": [],
                "rationale": "No proven relation.", "confidence": "low"}
        with patch.object(model, "call_model", return_value=json.dumps(good)) as mocked:
            result = discovery_local_model.classify(self.edge, self.cfg["model"])
        self.assertFalse(result["repair_attempted"])
        self.assertEqual(mocked.call_count, 1)

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
