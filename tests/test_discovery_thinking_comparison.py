"""Tests for the evidence-controlled thinking comparison."""
import unittest
from unittest.mock import patch

from core import discovery_thinking_comparison


class ThinkingComparisonTests(unittest.TestCase):
    def test_same_evidence_and_different_modes(self):
        graph = {"relationships": [
            {"from": "A", "to": "B", "project": "APS", "type": "related_to",
             "evidence": [{"citation": "DOC-1", "excerpt": "A integrates with B"}]},
        ]}
        cfg = {"model": {"endpoint": "http://localhost/test", "name": "local",
                         "max_tokens": 512, "timeout": 60, "temperature": 0.2}}
        calls = []

        def fake_classify(edge, model_cfg, use_cache=True):
            calls.append((edge, model_cfg["enable_thinking"], use_cache))
            return {"status": "unconfirmed_model_proposal",
                    "type": "integrates_with" if model_cfg["enable_thinking"] else "unresolved",
                    "citations": ["DOC-1"] if model_cfg["enable_thinking"] else [],
                    "confidence": "high" if model_cfg["enable_thinking"] else "low",
                    "rationale": "Test", "repair_attempted": False}

        with patch("core.discovery_local_model.classify", side_effect=fake_classify):
            result = discovery_thinking_comparison.compare(graph, cfg)
        self.assertEqual([x[1] for x in calls], [False, True])
        self.assertTrue(all(x[0] is graph["relationships"][0] for x in calls))
        self.assertTrue(all(x[2] is False for x in calls))
        self.assertEqual(result["reviewed"], 1)
        self.assertEqual(result["different_types"], 1)
        self.assertEqual(result["modes"]["on"]["valid"], 1)

    def test_failures_are_recorded_not_confirmed(self):
        graph = {"relationships": [
            {"from": "A", "to": "B", "project": "APS", "evidence": []},
        ]}
        cfg = {"model": {"endpoint": "http://localhost/test", "name": "local"}}
        with patch("core.discovery_local_model.classify", side_effect=ValueError("bad json")):
            result = discovery_thinking_comparison.compare(graph, cfg)
        self.assertEqual(result["modes"]["off"]["failures"], 1)
        self.assertEqual(result["modes"]["on"]["failures"], 1)


if __name__ == "__main__":
    unittest.main()
