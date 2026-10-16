"""Local model classification never approves unsupported relationships."""
import io
import json
import unittest
from unittest.mock import patch

from core import discovery_local_model


class LocalModelTests(unittest.TestCase):
    def setUp(self):
        self.edge = {"from": "ITK", "to": "SDX", "type": "depends_on",
                     "project": "APS", "evidence": [
                         {"citation": "jira:APS-1", "kind": "issue",
                          "excerpt": "ITK depends on SDX."}]}

    def _response(self, answer):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return json.dumps({"choices": [{"message": {
                    "content": json.dumps(answer)}}]}).encode("utf-8")
        return Response()

    def test_grounded_proposal_keeps_candidate_only(self):
        answer = {"type": "depends_on", "citations": ["jira:APS-1"],
                  "confidence": "medium", "rationale": "An explicit dependency."}
        with patch.object(discovery_local_model.request, "urlopen",
                          return_value=self._response(answer)):
            result = discovery_local_model.classify(
                self.edge, "http://127.0.0.1:8000/v1/chat/completions", "qwen")
        self.assertEqual(result["status"], "unconfirmed_model_proposal")
        self.assertEqual(result["citations"], ["jira:APS-1"])

    def test_rejects_unseen_citations(self):
        answer = {"type": "depends_on", "citations": ["jira:APS-999"],
                  "confidence": "high", "rationale": "Invented reference."}
        with patch.object(discovery_local_model.request, "urlopen",
                          return_value=self._response(answer)):
            with self.assertRaises(ValueError):
                discovery_local_model.classify(
                    self.edge, "http://localhost:8000/v1/chat/completions", "qwen")

    def test_blocks_remote_model_endpoints(self):
        for url in ["https://api.external.com/v1/chat/completions",
                    "http://example.com/v1/chat/completions",
                    "http://localhost:8000/unexpected"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                discovery_local_model._endpoint(url)

    def test_review_errors_are_not_confirmations(self):
        graph = {"relationships": [self.edge]}
        with patch.object(discovery_local_model, "classify",
                          side_effect=ValueError("Bad JSON")):
            result = discovery_local_model.review(
                graph, endpoint="http://localhost:8000/v1/chat/completions",
                model="local")
        self.assertEqual(result["results"][0]["model"]["status"], "model_error")
        self.assertEqual(result["results"][0]["model"]["type"], "unresolved")


if __name__ == "__main__":
    unittest.main()
