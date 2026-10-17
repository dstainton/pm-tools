"""Read-only, cited concept relationships from offline indexed documents.

Candidate identity is canonical within one project. Strict textual relation
patterns, rather than co-occurrence, generate typed candidate edges. No
relationship becomes a confirmed fact or changes user configuration.
"""
import re
import sqlite3
from collections import defaultdict

from core import discovery_concept_clusters, discovery_fts, discovery_term_relationships, discovery_evidence_priority
from core.discovery_identity import IdentityIndex
from core.discovery_contextual_candidates import _relationship

# Capture explicit dependencies to external tokens absent from the registry.
EXPLICIT_TOKENS = (
    ("depends_on", re.compile(r"\b(?P<a>[A-Z][A-Z0-9]{1,9})\s+depends\s+on\s+(?P<b>[A-Z][A-Z0-9]{1,9})\b")),
    ("integrates_with", re.compile(r"\b(?P<a>[A-Z][A-Z0-9]{1,9})\s+integrates\s+with\s+(?P<b>[A-Z][A-Z0-9]{1,9})\b")),
    ("part_of", re.compile(r"\b(?P<a>[A-Z][A-Z0-9]{1,9})\s+is\s+part\s+of\s+(?P<b>[A-Z][A-Z0-9]{1,9})\b")),
    ("delivered_by", re.compile(r"\b(?P<a>[A-Z][A-Z0-9]{1,9})\s+is\s+delivered\s+by\s+(?P<b>[A-Z][A-Z0-9]{1,9})\b")),
)



def discover(db_path, project=None, display_limit=100):
    if display_limit < 1:
        raise ValueError("display_limit must be positive")
    clusters = discovery_concept_clusters.clusters(db_path, project=project, limit=None)
    identity = IdentityIndex(clusters)
    identities = [{
        "project": item["project"], "canonical": item["canonical"],
        "aliases": item["aliases"], "status": item["review_status"],
        "ambiguous_aliases": item["ambiguous_aliases"],
        "citations": item["citations"], "concept_ids": item["concept_ids"]}
        for item in clusters]
    edges = {}
    documents = 0
    sources = defaultdict(int)

    def add(scope, a, b, relation, citation, kind, when, excerpt,
            source=None, source_key=None):
        a, b = identity.resolve(scope, a), identity.resolve(scope, b)
        if a.casefold() == b.casefold():
            return
        source = source or ("jira" if str(citation).startswith("jira:") else "confluence")
        group = discovery_evidence_priority.parent_group(
            scope, source, kind, source_key, citation)
        key = (scope, a.casefold(), b.casefold(), relation)
        item = edges.setdefault(key, {
            "project": scope, "from": a, "to": b, "type": relation,
            "status": "candidate", "evidence": []})
        candidate = {
            "citation": citation, "kind": kind, "event_time": when,
            "excerpt": excerpt.strip()[:400], "_group": group,
            "_priority": discovery_evidence_priority.priority(source, kind)}
        previous = next((ev for ev in item["evidence"] if ev["_group"] == group),
                        None)
        if previous is None:
            item["evidence"].append(candidate)
        elif ((candidate["_priority"], candidate["citation"]) <
              (previous["_priority"], previous["citation"])):
            item["evidence"].remove(previous)
            item["evidence"].append(candidate)

    db = sqlite3.connect(str(db_path))
    try:
        discovery_fts._init(db)
        sql = """SELECT project, source, source_key, citation, kind, event_time, title, body
                 FROM discovery_fts_documents"""
        args = ()
        if project:
            sql += " WHERE project=?"
            args = (project,)
        sql += " ORDER BY project, citation"
        for scope, source, source_key, cite, kind, when, title, body in db.execute(sql, args):
            documents += 1
            sources[source] += 1
            if discovery_evidence_priority.is_historical(source, kind):
                # Changelog rows remain available for terminology-history
                # analysis, but should not assert current dependencies.
                continue
            for fragment in [title or ""] + re.split(r"(?<=[.!?])\s+|[\r\n]+", body or ""):
                if not 15 <= len(fragment) <= 500:
                    continue
                for relation, pattern in EXPLICIT_TOKENS:
                    for match in pattern.finditer(fragment):
                        add(scope, match.group("a"), match.group("b"), relation,
                            cite, kind, when, fragment, source, source_key)
                hits = identity.mentions(scope, fragment)
                if len(hits) > 6:
                    continue
                for i, first in enumerate(hits):
                    for second in hits[i + 1:]:
                        if first[2].casefold() == second[2].casefold():
                            continue
                        relation, strength = _relationship(fragment, first, second)
                        if strength == 3 and relation:
                            add(scope, first[2], second[2], relation, cite,
                                kind, when, fragment, source, source_key)
        # Explicit rename records can contain previously unknown names; they
        # are hypotheses and must not be auto-registered as aliases.
        for entry in discovery_term_relationships.propose(
                db_path, project=project, limit=10000)["relationships"]:
            for ev in entry["evidence"]:
                add(entry["project"], entry["from"], entry["to"],
                    entry["relationship"], ev["citation"], ev.get("kind"),
                    ev.get("event_time"), ev.get("excerpt", ""))
    finally:
        db.close()
    relations = list(edges.values())
    for item in relations:
        item["evidence"].sort(key=lambda ev: (
            ev["_priority"], ev["citation"]))
        item["independent_sources"] = len(item["evidence"])
        for ev in item["evidence"]:
            del ev["_group"], ev["_priority"]
    relations.sort(key=lambda e: (-e["independent_sources"], e["project"] or "",
                                  e["type"], e["from"], e["to"]))
    identities.sort(key=lambda i: (i["project"] or "", i["canonical"].casefold()))
    return {
        "identity_total": len(identities), "identities": identities,
        "relationship_total": len(relations), "relationships": relations,
        "identity_ambiguous_count": sum(bool(i["ambiguous_aliases"]) for i in identities),
        "indexed_documents": documents, "indexed_source_counts": dict(sources),
        "method": "project_scoped_canonical_candidates_with_explicit_evidence",
    }
