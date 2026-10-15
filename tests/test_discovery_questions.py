"""Phase 2B clarification questions remain bounded and unconfirmed."""
import unittest

from core import discovery, discovery_questions


class ClarificationTests(unittest.TestCase):
    def test_questions_reference_evidence_without_inventing_definitions(self):
        cfg = {"jira": {"project": "ABC"},
               "products": [{"name": "Product", "abbrev": "P"}],
               "workstreams": [{"name": "Gateway", "abbrev": "GW",
                                "product": "P", "components": ["Gateway"]}]}
        report = discovery.inspect(cfg)
        ws = report["workstreams"][0]
        ws["evidence"] = [
            {"kind": "Confluence", "state": "retrieved", "reference": "22"},
            {"kind": "Jira Epics", "state": "retrieved",
             "items": [{"key": "ABC-3", "title": "Epic three", "updated": "2026-10-01"},
                       {"key": "ABC-4", "title": "Epic four", "updated": "2026-10-02"}]}]
        report = discovery_questions.attach(report)
        self.assertEqual(len(report["clarifications"]), 2)
        item = report["clarifications"][1]
        self.assertEqual(item["references"], ["Confluence page 22", "ABC-3", "ABC-4"])
        self.assertIn("needs review", discovery.markdown(report))
        self.assertIn("Questions for review", discovery.summary(report))
        self.assertIn("Purpose: unknown", discovery.markdown(report))

    def test_queue_bounded_even_with_many_unconfigured_entities(self):
        report = {"products": [], "workstreams": [
            {"name": "Stream " + str(i), "abbrev": str(i)}
            for i in range(20)]}
        self.assertEqual(len(discovery_questions.build(report)), 5)

    def test_implicit_product_does_not_get_false_goal_question(self):
        report = {"products": [{"name": "Unassigned", "abbrev": "UNASSIGNED",
                                "implicit": True, "goal": None}],
                  "workstreams": []}
        self.assertEqual(discovery_questions.build(report), [])


if __name__ == "__main__":
    unittest.main()
