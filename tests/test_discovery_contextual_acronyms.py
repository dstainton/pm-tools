"""Guard against false concept references from ordinary-language acronyms."""
import unittest
from unittest.mock import patch

from core import discovery_contextual_candidates as contextual


class _Rows:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, _query, _params):
        return [
            ("APS", "jira:APS-1", "comment", None, "",
             "The team DID NOT test the user testing workflow."),
            ("APS", "jira:APS-2", "issue", None, "",
             "Validate SDX data dictionary mappings against the ADR glossary."),
        ]


class ContextualAcronymTests(unittest.TestCase):
    def test_ordinary_did_is_not_a_concept_and_mapping_is_prioritized(self):
        concepts = [
            {"project": "APS", "canonical": "Directed Identifier", "aliases": ["DID"]},
            {"project": "APS", "canonical": "user testing", "aliases": ["UT"]},
            {"project": "APS", "canonical": "Secure data exchange", "aliases": ["SDX"]},
            {"project": "APS", "canonical": "Authoritative data register", "aliases": ["ADR"]},
        ]
        with patch.object(contextual.discovery_concept_clusters, "clusters",
                          return_value=concepts), \
             patch.object(contextual.sqlite3, "connect", return_value=_Rows()), \
             patch.object(contextual.discovery_fts, "_init"):
            found = contextual.candidates("unused", project="APS")
        self.assertFalse(any("DID" in (entry["from"], entry["to"]) for entry in found))
        self.assertTrue(any(
            set((entry["from"], entry["to"])) == {"SDX", "ADR"}
            and entry["signal_sources"] == 1
            for entry in found
        ))


if __name__ == "__main__":
    unittest.main()
