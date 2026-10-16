"""Read-only, cited candidate concept graph from indexed evidence.

Identity hypotheses are separate from typed relationships. No candidate is
promoted into the confirmed registry and co-occurrence cannot assert ownership.
"""
import re
import sqlite3
from collections import defaultdict

from core import discovery_concept_clusters, discovery_fts, discovery_term_relationships


RELATIONS = (
    ("depends_on", re.compile(r"\b(?P<a>[A-Z][A-Z0-9]{1,9})\s+depends\s+on\s+(?P<b>[A-Z][A-Z0-9]{1,9})\b")),
    ("integrates_with", re.compile(r"\b(?P<a>[A-Z][A-Z0-9]{1,9})\s+integrates\s+with\s+(?P<b>[A-Z][A-Z0-9]{1,9})\b")),
    ("part_of", re.compile(r"\b(?P<a>[A-Z][A-Z0-9]{1,9})\s+is\s+part\s+of\s+(?P<b>[A-Z][A-Z0-9]{1,9})\b")),
    ("delivered_by", re.compile(r"\b(?P<a>[A-Z][A-Z0-9]{1,9})\s+is\s+delivered\s+by\s+(?P<b>[A-Z][A-Z0-9]{1,9})\b")),
)


def _token(text, term):
    return re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.I) is not None


def discover(db_path, project=None, display_limit=100):
    """Return complete candidate counts and bounded display, with citations."""
    if display_limit < 1:
        raise ValueError("display_limit must be positive")
    clusters = discovery_concept_clusters.clusters(db_path, project=project, limit=None)
    identities = []
    aliases = defaultdict(set)
    for item in clusters:
        identities.append({
            "project": item["project"], "canonical": item["canonical"],
            "aliases": item["aliases"], "status": item["review_status"],
            "ambiguous_aliases": item["ambiguous_aliases"],
            "citations": item["citations"], "concept_ids": item["concept_ids"]})
        for term in item["aliases"]:
            aliases[(item["project"], term.casefold())].add(item["canonical"])
    edges = {}
    db = sqlite3.connect(str(db_path))
    try:
        discovery_fts._init(db)
        sql = """SELECT project, citation, kind, event_time, title, body
                 FROM discovery_fts_documents"""
        args = ()
        if project:
            sql += " WHERE project=?"
            args = (project,)
        for scope, cite, kind, when, title, body in db.execute(sql, args):
            # Titles are especially useful for structural/operational cues;
            # source bodies may also state relationships explicitly.
            for fragment in [title or ""] + re.split(r"(?<=[.!?])\s+|[\r\n]+", body or ""):
                if len(fragment) > 500:
                    continue
                for relation, pattern in RELATIONS:
                    for match in pattern.finditer(fragment):
                        a, b = match.group("a"), match.group("b")
                        if a == b:
                            continue
                        key = (scope, a, b, relation)
                        edge = edges.setdefault(key, {
                            "project": scope, "from": a, "to": b,
                            "type": relation, "status": "candidate",
                            "evidence": []})
                        if not any(e["citation"] == cite for e in edge["evidence"]):
                            edge["evidence"].append({
                                "citation": cite, "kind": kind, "event_time": when,
                                "excerpt": fragment.strip()[:300]})
        # The explicit relationship parser remains a separate source of edges.
        for entry in discovery_term_relationships.propose(
                db_path, project=project, limit=10000)["relationships"]:
            relation = entry["relationship"]
            key = (entry["project"], entry["from"], entry["to"], relation)
            edge = edges.setdefault(key, {
                "project": entry["project"], "from": entry["from"],
                "to": entry["to"], "type": relation,
                "status": "candidate", "evidence": []})
            for ev in entry["evidence"]:
                if not any(e["citation"] == ev["citation"] for e in edge["evidence"]):
                    edge["evidence"].append(ev)
    finally:
        db.close()
    relations = list(edges.values())
    for edge in relations:
        edge["independent_sources"] = len(edge["evidence"])
    relations.sort(key=lambda e: (-e["independent_sources"], e["project"] or "",
                                  e["type"], e["from"], e["to"]))
    identities.sort(key=lambda i: (i["project"] or "", i["canonical"].casefold()))
    return {
        "identity_total": len(identities),
        "identities": identities[:display_limit],
        "relationship_total": len(relations),
        "relationships": relations[:display_limit],
        "identity_ambiguous_count": sum(bool(i["ambiguous_aliases"]) for i in identities),
        "method": "cited_candidate_graph_no_auto_confirmation",
    }
