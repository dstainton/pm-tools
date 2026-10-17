"""Evidence priorities: one Jira issue, not one vote per comment/change."""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from core import (
    discovery_concepts, discovery_concept_graph, discovery_contextual_candidates,
    discovery_evidence_priority, discovery_fts, discovery_profile_leads,
)


class EvidencePriorityTests(unittest.TestCase):
    def test_parent_issue_groups_comments_and_changes(self):
        f = discovery_evidence_priority.parent_group
        issue = f("APS", "jira", "issue", "APS-100", "jira:APS-100")
        comment = f("APS", "jira", "comment", "APS-100", "jira:APS-100#comment-1")
        change = f("APS", "jira", "change", "APS-100", "jira:APS-100#changelog-2")
        self.assertEqual(issue, comment)
        self.assertEqual(issue, change)
        self.assertNotEqual(issue, f("OTHER", "jira", "issue",
                                     "APS-100", "jira:APS-100"))
        self.assertEqual(discovery_evidence_priority.priority(
            "confluence", "confluence_page"), 0)
        self.assertLess(discovery_evidence_priority.priority("jira", "issue"),
                        discovery_evidence_priority.priority("jira", "change"))

    def test_leads_prefer_confluence_and_jira_issues_not_changelog_volume(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "index.sqlite"
            with closing(sqlite3.connect(str(path))) as db:
                discovery_fts._init(db)
                def add(doc_id, source, source_key, kind, title, body, citation):
                    discovery_fts._put(
                        db, doc_id, source_key, "APS", kind, None, None,
                        title, body, citation, source=source)
                add("c1", "confluence", "400", "confluence_page",
                    "Integration Toolkit capabilities",
                    "Integration Toolkit provides guidance and onboarding for API teams.",
                    "confluence:400")
                add("i1", "jira", "APS-101", "issue",
                    "Integration Toolkit delivery",
                    "Integration Toolkit provides technical onboarding for API developers.",
                    "jira:APS-101")
                add("i2", "jira", "APS-102", "issue",
                    "Developer experience",
                    "Integration Toolkit supports API discovery and navigation.",
                    "jira:APS-102")
                for n in range(15):
                    add("cm" + str(n), "jira", "APS-101", "comment",
                        "Integration Toolkit comment",
                        "Integration Toolkit provides an onboarding service to API teams.",
                        "jira:APS-101#comment-" + str(n))
                    add("ch" + str(n), "jira", "APS-101", "change",
                        "Integration Toolkit changelog",
                        "Integration Toolkit moved within service management.",
                        "jira:APS-101#changelog-" + str(n))
                db.commit()
            cfg = {"workstreams": [
                {"name": "Integration Toolkit", "abbrev": "ITK", "project": "APS"}]}
            report = discovery_profile_leads.build(
                path, cfg, project="APS", per_entity=5)
            self.assertEqual(report["indexed_documents_scanned"], 33)
            self.assertEqual(report["jira_unique_issues"], 2)
            self.assertEqual(report["jira_supporting_records"], 30)
            self.assertEqual(report["indexed_kind_counts"]["jira:issue"], 2)
            self.assertEqual(report["indexed_kind_counts"]["jira:comment"], 15)
            self.assertEqual(report["indexed_kind_counts"]["jira:change"], 15)
            entity = report["entities"][0]
            self.assertEqual(entity["documents_matched"], 3)
            self.assertEqual(entity["evidence_records_matched"], 33)
            self.assertEqual(
                [lead["citation"] for lead in entity["leads"]],
                ["confluence:400", "jira:APS-101", "jira:APS-102"])

    def test_contextual_and_typed_edges_are_not_inflated_by_issue_activity(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "index.sqlite"
            for key, title, alias in [
                ("itk", "Integration Toolkit", "ITK"),
                ("sdx", "Secure Data Exchange", "SDX"),
            ]:
                discovery_concepts.register(path, key, title, project="APS")
                discovery_concepts.alias(
                    path, key, alias, "abbreviation", "jira:seed-" + key)
            with closing(sqlite3.connect(str(path))) as db:
                discovery_fts._init(db)
                def add(doc_id, source, source_key, kind, citation, body):
                    discovery_fts._put(
                        db, doc_id, source_key, "APS", kind, None, None,
                        "", body, citation, source=source)
                add("p", "confluence", "500", "confluence_page", "confluence:500",
                    "Integration Toolkit depends on Secure Data Exchange for token handling.")
                add("i", "jira", "APS-120", "issue", "jira:APS-120",
                    "Integration Toolkit depends on Secure Data Exchange for secure exchange.")
                for n in range(20):
                    add("cm" + str(n), "jira", "APS-120", "comment",
                        "jira:APS-120#comment-" + str(n),
                        "Integration Toolkit depends on Secure Data Exchange for new features.")
                    add("ch" + str(n), "jira", "APS-120", "change",
                        "jira:APS-120#changelog-" + str(n),
                        "Integration Toolkit depends on Secure Data Exchange.")
                db.commit()
            result = discovery_contextual_candidates.candidates(
                path, project="APS")
            item = next(row for row in result if {
                row["from"], row["to"]} == {
                "Integration Toolkit", "Secure Data Exchange"})
            self.assertEqual(item["independent_sources"], 2)
            self.assertEqual(item["descriptive_sources"], 2)
            self.assertEqual([ev["citation"] for ev in item["evidence"]],
                             ["confluence:500", "jira:APS-120"])
            graph = discovery_concept_graph.discover(path, project="APS")
            edge = next(row for row in graph["relationships"]
                        if row["type"] == "depends_on")
            self.assertEqual(edge["independent_sources"], 2)
            self.assertEqual([ev["citation"] for ev in edge["evidence"]],
                             ["confluence:500", "jira:APS-120"])


if __name__ == "__main__":
    unittest.main()
