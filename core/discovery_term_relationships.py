"""Cited terminology relationship proposals from explicit source language.

No inferred synonyms from co-occurrence. Suggestions are never written into
the confirmed concept/alias registry, and retain original source wording.
"""
import re
import sqlite3
from collections import defaultdict

from core import discovery_fts


# Restrict matching to explicit entity-like labels. Broad case-insensitive spans
# previously turned ordinary clauses into fictitious product relationships.
HISTORICAL = re.compile(
    r"(?P<new>[A-Za-z][A-Za-z0-9 /&.-]{1,90}?)\\s*"
    r"\\(\\s*(?:formerly|previously|earlier called)\\s+"
    r"(?P<old>[A-Za-z][A-Za-z0-9 /&.-]{1,70}?)\\s*\\)", re.I)
RENAMED = re.compile(
    r"(?P<old>[A-Za-z][A-Za-z0-9 /&.-]{1,90}?)\\s+"
    r"(?:was renamed to|has been renamed to|renamed to|is now called)\\s+"
    r"(?P<new>[A-Za-z][A-Za-z0-9 /&.-]{1,90}?)(?=[;,\\n]|$)", re.I)
REPLACED = re.compile(
    r"(?P<new>[A-Za-z][A-Za-z0-9 /&.-]{1,90}?)\\s+"
    r"(?:replaces|supersedes)\\s+"
    r"(?P<old>[A-Za-z][A-Za-z0-9 /&.-]{1,90}?)(?=[;,\\n]|$)", re.I)

STOPWORDS = {"and", "how", "which", "this", "that", "since", "the",
             "a", "an", "who", "it", "they", "we", "you", "i",
             "someone", "something", "what", "there", "from",
             "noted", "fails", "revealed", "between", "also",
             "good", "share", "somewhere", "new", "current", "use",
             "is", "was", "are", "to", "in", "on", "of", "for"}

def _clean(term):
    return " ".join(term.split()).strip(" :-.,()")

def _entity(term):
    """A short name-like phrase, not a clause or generic pronoun."""
    if not term or len(term) > 72:
        return False
    words = term.replace("/", " ").replace("-", " ").split()
    if not 1 <= len(words) <= 8:
        return False
    if any(w.casefold() in STOPWORDS for w in words[:1]):
        return False
    significant = [w for w in words if w.casefold() not in
                   {"of", "and", "for", "the", "to"}]
    return bool(significant) and all(
        w[0].isupper() or any(ch.isdigit() for ch in w)
        or ("." in w and w[0].isalpha()) for w in significant)

def _matches(sentence):
    # Parenthesized former names may occur in a longer sentence. Start after
    # the nearest clause delimiter to avoid swallowing preceding prose.
    for match in HISTORICAL.finditer(sentence):
        prefix = match.group("new")
        prefix = re.split(r"[,;:]|\\s{2,}", prefix)[-1]
        # Prefer the smallest capitalized suffix, e.g. 'OrgBook', rather than
        # treating introductory text as part of the product name.
        words = prefix.split()
        while len(words) > 1 and not _entity(" ".join(words)):
            words.pop(0)
        new, old = _clean(" ".join(words)), _clean(match.group("old"))
        if _entity(new) and _entity(old):
            yield "historical_name", new, old
    for pattern, relation in ((RENAMED, "renamed_to"),
                              (REPLACED, "replaces")):
        for match in pattern.finditer(sentence):
            a, b = _clean(match.group("old" if relation == "renamed_to" else "new")), _clean(match.group("new" if relation == "renamed_to" else "old"))
            if _entity(a) and _entity(b):
                yield relation, a, b


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
                    for relation, a, b in _matches(sentence):
                        if a.casefold() == b.casefold():
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
