"""Cited terminology relationship proposals from explicit source language.

No inferred synonyms from co-occurrence. Suggestions are never written into
the confirmed concept/alias registry, and retain original source wording.
"""
import re
import sqlite3
from collections import defaultdict

from core import discovery_fts


# These are intentionally narrow lexical templates, not semantic proof.
PATTERNS = (
    (re.compile(r"(?P<new>[A-Z][A-Za-z0-9 /&-]{2,65}?)\s*\(\s*(?:formerly|previously|earlier called)\s+(?P<old>[A-Z][A-Za-z0-9 /&-]{1,65}?)\s*\)", re.I),
     "historical_name", "new", "old"),
    (re.compile(r"(?P<old>[A-Z][A-Za-z0-9 /&-]{2,65}?)\s+(?:was renamed to|has been renamed to|renamed to|is now called)\s+(?P<new>[A-Z][A-Za-z0-9 /&-]{2,65}?)(?=[.;,\n]|$)", re.I),
     "renamed_to", "old", "new"),
    (re.compile(r"(?P<new>[A-Z][A-Za-z0-9 /&-]{2,65}?)\s+(?:replaces|supersedes)\s+(?P<old>[A-Z][A-Za-z0-9 /&-]{2,65}?)(?=[.;,\n]|$)", re.I),
     "replaces", "new", "old"),
)


def _clean(term):
    return " ".join(term.split()).strip(" :-.,()")


def propose(db_path, project=None, limit=100):
    """Scan local indexed source text; return bounded, cited candidate edges."""
    if limit < 1:
        raise ValueError("limit must be positive")
    db = sqlite3.connect(str(db_path))
    try:
        discovery_fts._init(db)
        query = """SELECT project, citation, title, body, kind, event_time
                   FROM discovery_fts_documents"""
        args = []
        if project:
            query += " WHERE project=?"
            args.append(project)
        query += " ORDER BY citation"
        proposals = {}
        sources = set()
        for scope, citation, title, body, kind, when in db.execute(query, args):
            sources.add((scope, citation))
            # Work sentence-by-sentence to prevent cross-topic matches.
            for raw in (title or "", body or ""):
                for sentence in re.split(r"(?<=[.!?])\s+|[\r\n]+", raw):
                    if len(sentence) > 800:
                        continue
                    for pattern, relation, left, right in PATTERNS:
                        for match in pattern.finditer(sentence):
                            a, b = _clean(match.group(left)), _clean(match.group(right))
                            if not a or not b or a.casefold() == b.casefold():
                                continue
                            key = (scope, relation, a.casefold(), b.casefold())
                            record = proposals.setdefault(key, {
                                "project": scope, "relationship": relation,
                                "from": a, "to": b, "status": "candidate",
                                "evidence": []})
                            if citation not in {ev["citation"] for ev in record["evidence"]}:
                                record["evidence"].append({
                                    "citation": citation, "kind": kind,
                                    "event_time": when,
                                    "excerpt": sentence.strip()[:300]})
        result = list(proposals.values())
        for item in result:
            item["evidence_count"] = len(item["evidence"])
        result.sort(key=lambda x: (-x["evidence_count"],
                                   x["project"] or "", x["from"].casefold(), x["to"].casefold()))
        return {"examined_documents": len(sources),
                "relationships": result[:limit],
                "total_candidates": len(result)}
    finally:
        db.close()
