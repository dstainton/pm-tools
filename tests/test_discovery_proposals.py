"""Grounded discovery proposals stay bounded, referenced, and unconfirmed."""
import argparse
import unittest
from unittest.mock import patch

from commands import discover
from core import discovery, discovery_proposals

CFG = {
    "jira": {"project": "ABC"}, "model": {"name": "local"},
    "products": [{"name": "Platform", "abbrev": "PLAT"}],
    "workstreams": [{"name": "Gateway", "abbrev": "GW",
                     "product": "PLAT", "components": ["Gateway"]}],
}


class ProposalTests(unittest.TestCase):
    def _report(self):
        report = discovery.inspect(CFG)
        report["workstreams"][0]["evidence"] = [
            {"kind": "Confluence", "state": "retrieved",
             "reference": "44", "excerpt": "Gateway provides routing.",
             "updated": "2026-10-01"},
            {"kind": "Jira Epics", "state": "retrieved",
             "items": [{"key": "ABC-1", "title": "API gateway routing",
                        "updated": "2026-10-02"}]}]
        return report

    def test_only_supported_tags_and_fields_survive(self):
        report = self._report()
        responses = [[{"field": "product_goal", "text": "Enable integration",
                       "refs": ["J:ABC-1"]}],
                     [{"field": "purpose", "text": "Operate routing", "refs": ["C:44"]},
                      {"field": "exclusions", "text": "Never handle identity",
                       "refs": ["J:MADEUP"]},
                      {"field": "wrong", "text": "Invent", "refs": ["C:44"]}]]
        with patch("core.discovery_proposals.model.call_model_json",
                   side_effect=[(x, None) for x in responses]) as model_call, patch(
                   "core.discovery_proposals.model.announce"), patch(
                   "core.discovery_proposals.model.tick"), patch(
                   "core.discovery_proposals.progress.finish"):
            discovery_proposals.propose(CFG, report)
        self.assertEqual(model_call.call_count, 2)
        self.assertEqual(len(report["workstreams"][0]["proposals"]), 1)
        self.assertEqual(report["workstreams"][0]["proposals"][0]["refs"], ["C:44"])
        self.assertIn("unconfirmed", discovery.markdown(report))
        self.assertIn("C:44", discovery.summary(report))

    def test_missing_evidence_skips_model(self):
        with patch("core.discovery_proposals.model.call_model_json") as call, patch(
                "core.discovery_proposals.model.announce"), patch(
                "core.discovery_proposals.progress.finish"):
            report = discovery_proposals.propose(CFG, discovery.inspect(CFG))
        call.assert_not_called()
        self.assertIn("Insufficient", report["workstreams"][0]["proposal_note"])

    def test_bad_model_reply_not_treated_as_fact(self):
        report = self._report()
        with patch("core.discovery_proposals.model.call_model_json",
                   return_value=(None, "invalid")), patch(
                   "core.discovery_proposals.model.announce"), patch(
                   "core.discovery_proposals.model.tick"), patch(
                   "core.discovery_proposals.progress.finish"):
            discovery_proposals.propose(CFG, report)
        self.assertEqual(report["workstreams"][0]["proposals"], [])
        self.assertIn("unavailable", report["workstreams"][0]["proposal_note"])

    def test_propose_requires_explicit_enrichment(self):
        args = argparse.Namespace(project=None, product=None, workstream=None,
                                  enrich=False, propose=True, questions=False,
                                  export=False)
        with patch("core.discovery_proposals.propose") as call:
            with self.assertRaises(SystemExit):
                discover.run(CFG, args)
        call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
