"""Read-only, project-scoped contextual relationship candidates.

Concepts are canonicalized before pair generation. Source proximity is a
retrieval heuristic, not proof of ownership or a confirmed graph edge.
"""
import re
import sqlite3
from collections import defaultdict

from core import discovery_fts, discovery_concept_clusters, discovery_evidence_priority
from core.discovery_identity import IdentityIndex

RELATION_SIGNAL = re.compile(
    r"\b(?:integrat\w*|depend\w*|consum\w*|provid\w*|deliver\w*|"
    r"connect\w*|replac\w*|migrat\w*|calls?|exchang\w*|"
    r"mapp?ings?|glossary|onboard\w*|validat\w*|"
    r"source of truth|conforms? to)\b", re.IGNORECASE)

# Explicit directional phrases between entity mentions. These only provide
# candidate hints, and are checked against source citations downstream.
DIRECTED = (
    ("depends_on", re.compile(r"^\s+depends?\s+on\s+$", re.I)),
    ("integrates_with", re.compile(r"^\s+integrates?\s+with\s+$", re.I)),
    ("part_of", re.compile(r"^\s+(?:is\s+)?part\s+of\s+$", re.I)),
    ("delivered_by", re.compile(r"^\s+is\s+delivered\s+by\s+$", re.I)),
    ("uses", re.compile(r"^\s+uses?\s+$", re.I)),
)


def _relationship(fragment, earlier, later):
    between = fragment[earlier[1]:later[0]]
    for kind, pattern in DIRECTED:
        if pattern.search(between):
            return kind, 3
    if (re.search(r"\bvalidat\w*\b", fragment[:earlier[0]], re.I)
            and re.search(r"\bagainst\b", between, re.I)):
        return "validated_against", 3
    # Do not rate broad document-instruction verbs ("use this section",
    # "publish the docs") as evidence of a business dependency.
    if RELATION_SIGNAL.search(between):
        return None, 1
    return None, 0


def candidates(db_path, project=None, limit=30):
    """Return source-cited candidate pairs ordered by relationship evidence.

    limit=None returns every candidate. Alias ambiguity, mixed projects and
    occurrences of ordinary English words as acronyms are excluded.
    """
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    clusters = discovery_concept_clusters.clusters(db_path, project=project, limit=None)
    identity = IdentityIndex(clusters)
    matches = {}
    db = sqlite3.connect(str(db_path))
    try:
        discovery_fts._init(db)
        sql = ("SELECT project, source, source_key, citation, kind, event_time, title, body "
               "FROM discovery_fts_documents")
        args = ()
        if project:
            sql += " WHERE project=?"
            args = (project,)
        sql += " ORDER BY project, citation"
        for scope, source, source_key, citation, kind, when, title, body in db.execute(sql, args):
            # History is evidence of past membership, not a primary source of
            # current product relationships. It remains in the FTS index.
            if discovery_evidence_priority.is_historical(source, kind):
                continue
            group = discovery_evidence_priority.parent_group(
                scope, source, kind, source_key, citation)
            priority = discovery_evidence_priority.priority(source, kind)
            for fragment in [title or ""] + re.split(r"(?<=[.!?])\s+|[\r\n]+", body or ""):
                if not 15 <= len(fragment) <= 450:
                    continue
                hits = identity.mentions(scope, fragment)
                # A list of many concepts or a table of contents is poor
                # relational evidence, even if it contains a generic verb.
                if len({h[2].casefold() for h in hits}) < 2 or len(hits) > 8:
                    continue
                for i, a in enumerate(hits):
                    for b in hits[i + 1:]:
                        if a[2].casefold() == b[2].casefold():
                            continue
                        pair = tuple(sorted((a[2], b[2]), key=str.casefold))
                        key = (scope, pair[0].casefold(), pair[1].casefold())
                        relation, strength = _relationship(fragment, a, b)
                        record = matches.setdefault(key, {
                            "project": scope, "from": pair[0], "to": pair[1],
                            "type": "unresolved", "status": "candidate",
                            "evidence": [], "relationship_hints": []})
                        if relation:
                            hint = {"type": relation, "from": a[2], "to": b[2],
                                    "citation": citation}
                            if hint not in record["relationship_hints"]:
                                record["relationship_hints"].append(hint)
                        candidate = {
                            "citation": citation, "source": source, "kind": kind,
                            "event_time": when, "excerpt": fragment.strip(),
                            "relationship_signal": strength > 0,
                            "signal_strength": strength, "_group": group,
                            "_priority": priority}
                        # A comment and a dozen changelog entries attached to
                        # one Jira issue do not count as independent sources.
                        # Prefer the issue description over its comments;
                        # within a class, prefer explicit relationship wording.
                        previous = next((item for item in record["evidence"]
                                         if item["_group"] == group), None)
                        if previous is None:
                            record["evidence"].append(candidate)
                        elif ((-strength, candidate["_priority"], citation) <
                              (-previous["signal_strength"], previous["_priority"],
                               previous["citation"])):
                            record["evidence"].remove(previous)
                            record["evidence"].append(candidate)
        output = list(matches.values())
        for item in output:
            item["evidence"].sort(
                key=lambda ev: (ev["_priority"], -ev["signal_strength"], ev["citation"]))
            item["independent_sources"] = len(item["evidence"])
            item["descriptive_sources"] = sum(
                ev["_priority"] <= 1 for ev in item["evidence"])
            item["signal_sources"] = sum(bool(e["signal_strength"]) for e in item["evidence"])
            item["strong_sources"] = sum(e["signal_strength"] == 3 for e in item["evidence"])
            item["descriptive_strong_sources"] = sum(
                ev["_priority"] <= 1 and ev["signal_strength"] == 3
                for ev in item["evidence"])
            for ev in item["evidence"]:
                del ev["_group"], ev["_priority"]
        # Explicit relationships in descriptive sources beat numerous
        # peripheral comments. High-volume Jira histories add no score.
        output.sort(key=lambda x: (
            -x["descriptive_strong_sources"], -x["descriptive_sources"],
            -x["strong_sources"], -x["signal_sources"],
            -x["independent_sources"], x["project"] or "",
            x["from"].casefold(), x["to"].casefold()))
        return output if limit is None else output[:limit]
    finally:
        db.close()
