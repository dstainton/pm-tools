"""Tests for the Phase 2A benchmark contract and scoring."""
import copy
import unittest

from core.discovery_benchmark import evaluate


def sample():
    case = {
        "case_id": "synth-1", "split": "development",
        "reviewed_by": "human-reviewer", "reviewed_at": "2026-10-17",
        "source": {"project": "DEMO", "citation": "confluence:100",
                   "revision": "rev1", "start": 0, "end": 40,
                   "quote": "Example Service provides API lookup."},
        "expected": {
            "entities": [{"id": "demo:service", "name": "Example Service",
                          "roles": ["service"]}],
            "claims": [{"subject_id": "demo:service", "predicate": "provides",
                        "object": "API lookup", "polarity": "positive",
                        "modality": "actual",
                        "evidence_quote": "provides API lookup"}]}}
    prediction = {
        "case_id": "synth-1", "entities": copy.deepcopy(case["expected"]["entities"]),
        "claims": [dict(case["expected"]["claims"][0],
                        citation="confluence:100")]}
    return {"schema_version": 1, "cases": [case]}, {
        "schema_version": 1, "predictions": [prediction]}


class BenchmarkTests(unittest.TestCase):
    def test_exact_matches(self):
        ref, pred = sample()
        report = evaluate(ref, pred)
        self.assertEqual(report["coverage"], 1.0)
        self.assertEqual(report["entities"]["precision"], 1.0)
        self.assertEqual(report["claims"]["recall"], 1.0)

    def test_missing_prediction_counts_as_false_negative(self):
        ref, pred = sample()
        pred["predictions"] = []
        report = evaluate(ref, pred)
        self.assertEqual(report["coverage"], 0)
        self.assertEqual(report["claims"]["false_negative"], 1)
        self.assertEqual(report["claims"]["recall"], 0)

    def test_incorrect_claim_counts_both_error_types(self):
        ref, pred = sample()
        pred["predictions"][0]["claims"][0]["object"] = "Data hosting"
        report = evaluate(ref, pred)
        self.assertEqual(report["claims"]["true_positive"], 0)
        self.assertEqual(report["claims"]["false_positive"], 1)
        self.assertEqual(report["claims"]["false_negative"], 1)

    def test_interest_holder_role_and_both_label_sources(self):
        ref, pred = sample()
        ref["cases"][0]["source"]["jira_labels"] = ["delivery", "identity"]
        ref["cases"][0]["source"]["confluence_labels"] = ["architecture"]
        role = {"id": "demo:interest", "name": "Service Consumers",
                "roles": ["interest_holder"]}
        ref["cases"][0]["expected"]["entities"].append(role)
        pred["predictions"][0]["entities"].append(role.copy())
        result = evaluate(ref, pred)
        self.assertEqual(result["entities"]["recall"], 1.0)

    def test_malformed_jira_or_confluence_labels_rejected(self):
        for key in ("jira_labels", "confluence_labels"):
            with self.subTest(key=key):
                ref, pred = sample()
                ref["cases"][0]["source"][key] = "not-an-array"
                with self.assertRaisesRegex(ValueError, key):
                    evaluate(ref, pred)

    def test_deprecated_stakeholder_role_rejected(self):
        ref, pred = sample()
        ref["cases"][0]["expected"]["entities"][0]["roles"] = ["stakeholder"]
        with self.assertRaisesRegex(ValueError, "roles"):
            evaluate(ref, pred)

    def test_invalid_citation_rejected(self):
        ref, pred = sample()
        pred["predictions"][0]["claims"][0]["citation"] = "jira:OTHER-1"
        with self.assertRaisesRegex(ValueError, "citation"):
            evaluate(ref, pred)

    def test_quote_outside_source_span_rejected(self):
        ref, pred = sample()
        pred["predictions"][0]["claims"][0]["evidence_quote"] = "invented wording"
        with self.assertRaisesRegex(ValueError, "source span"):
            evaluate(ref, pred)

    def test_unreviewed_reference_rejected(self):
        ref, pred = sample()
        del ref["cases"][0]["reviewed_by"]
        with self.assertRaisesRegex(ValueError, "human-reviewed"):
            evaluate(ref, pred)

    def test_illustrative_reference_rejected(self):
        ref, pred = sample()
        ref["cases"][0]["illustrative_only"] = True
        with self.assertRaisesRegex(ValueError, "human-reviewed"):
            evaluate(ref, pred)

    def test_unknown_prediction_case_rejected(self):
        ref, pred = sample()
        pred["predictions"][0]["case_id"] = "other"
        with self.assertRaisesRegex(ValueError, "Unknown"):
            evaluate(ref, pred)

    def test_duplicate_case_rejected(self):
        ref, pred = sample()
        pred["predictions"].append(copy.deepcopy(pred["predictions"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            evaluate(ref, pred)

    def test_directionality_is_part_of_claim_tuple(self):
        ref, pred = sample()
        pred["predictions"][0]["claims"][0]["predicate"] = "depends_on"
        self.assertEqual(evaluate(ref, pred)["claims"]["recall"], 0)


if __name__ == "__main__":
    unittest.main()
