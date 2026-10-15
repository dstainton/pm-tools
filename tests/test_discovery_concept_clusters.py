"""Clustering preserves competing acronym meanings and original citations."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from core import discovery_concepts, discovery_concept_clusters


class ClusterTests(unittest.TestCase):
    def test_spellings_group_but_conflicting_aliases_do_not(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.sqlite"
            pairs = [
                ("one", "API Program Services", "APS", "jira:APS-1", "APS"),
                ("two", "API Programme Services", "APS", "confluence:15", "APS"),
                ("three", "Forest Operations Map", "FOM", "jira:APS-3", "APS"),
                ("four", "Forest Operations Management", "FOM", "jira:APS-4", "APS"),
                ("five", "Forest Operations Map", "FOM", "jira:OTHER-1", "OTHER"),
            ]
            for cid, name, alias, citation, project in pairs:
                discovery_concepts.register(path, cid, name, project=project)
                discovery_concepts.alias(path, cid, alias, "abbreviation", citation)
            clusters = discovery_concept_clusters.clusters(path, project="APS")
            aps = next(c for c in clusters if c["canonical"] == "API Program Services")
            self.assertEqual(len(aps["variants"]), 2)
            self.assertEqual(aps["evidence_count"], 2)
            self.assertEqual(aps["review_status"], "candidate")
            foms = [c for c in clusters if c["canonical"].startswith("Forest")]
            self.assertEqual(len(foms), 2)
            self.assertTrue(all(c["ambiguous_aliases"] == ["FOM"] for c in foms))
            other = discovery_concept_clusters.clusters(path, project="OTHER")
            self.assertEqual(len(other), 1)
            self.assertEqual(other[0]["ambiguous_aliases"], [])
            again = discovery_concept_clusters.clusters(path, project="APS")
            self.assertEqual(clusters, again)


if __name__ == "__main__":
    unittest.main()
