"""Bounded, offline evaluation of terminology candidate pairs.

This is evidence triage, not a model judgement. Neither co-occurrence nor
matching acronyms establish identity. All decisions remain unconfirmed.
"""
import re
import sqlite3
from collections import defaultdict

from core import discovery_concept_clusters, discovery_fts, discovery_term_relationships


def _phrase(text, term):
    return re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.I) is not None


def _passages(text, a, b):
    # Window around a mention captures long Jira paragraphs and flattened
    # Confluence HTML without scanning unrelated passages.
    matches = list(re.finditer(r"(?<!\w)(?:" + re.escape(a) + "|" +
                              re.escape(b) + r")(?!\w)", text, re.I))
    result = []
    for hit in matches:
        start, end = max(0, hit.start() - 180), min(len(text), hit.end() + 180)
        fragment = text[start:end]
        if _phrase(fragment, a) and _phrase(fragment, b):
            if fragment not in result:
                result.append(fragment)
        if len(result) >= 3:
            break
    return result


def generate(db_path, project=None, max_pairs=100):
    """Generate pairs from explicit source relations and ambiguous clusters."""
    if max_pairs < 1:
        raise ValueError("max_pairs must be positive")
    pairs = {}
    explicit = discovery_term_relationships.propose(
        db_path, project=project, limit=1000)["relationships"]
    for entry in explicit:
        if entry["relationship"] == "historical_name":
            a, b = entry["from"], entry["to"]
        else:
            a, b = entry["from"], entry["to"]
        key = (entry["project"], a.casefold(), b.casefold())
        pairs[key] = {"project": entry["project"], "a": a, "b": b,
                      "basis": ["explicit:" + entry["relationship"]],
                      "source_citations": [e["citation"] for e in entry["evidence"]]}
    clusters = discovery_concept_clusters.clusters(db_path, project=project, limit=None)
    by_alias = defaultdict(list)
    for item in clusters:
        for alias in item["aliases"]:
            by_alias[(item["project"], alias.casefold())].append(item)
    for (scope, alias), items in by_alias.items():
        if len(items) < 2:
            continue
        # Competing expansions are comparison candidates, NOT synonyms.
        if len(items) > 12:
            continue
        for i, first in enumerate(items):
            for second in items[i + 1:]:
                a, b = sorted((first["canonical"], second["canonical"]))
                key = (scope, a.casefold(), b.casefold())
                record = pairs.setdefault(key, {
                    "project": scope, "a": a, "b": b,
                    "basis": [], "source_citations": []})
                record["basis"].append("competing_expansion:" + alias)
                record["source_citations"] = sorted(set(
                    record["source_citations"] + first["citations"] + second["citations"]))
    return sorted(pairs.values(), key=lambda x: (
        0 if any(v.startswith("explicit:") for v in x["basis"]) else 1,
        x["project"] or "", x["a"], x["b"]))[:max_pairs]


def evaluate(db_path, project=None, max_pairs=100, max_evidence=8):
    """Find bounded supporting/contrasting passages for each candidate pair."""
    if max_evidence < 1:
        raise ValueError("max_evidence must be positive")
    pairs = generate(db_path, project=project, max_pairs=max_pairs)
    db = sqlite3.connect(str(db_path))
    try:
        discovery_fts._init(db)
        output = []
        for item in pairs:
            a, b = item["a"], item["b"]
            evidence = []
            sql = """SELECT citation, source, kind, event_time, title, body
                     FROM discovery_fts_documents WHERE project IS ? ORDER BY citation"""
            for citation, source, kind, when, title, body in db.execute(
                    sql, (item["project"],)):
                for excerpt in _passages((title or "") + ". " + (body or ""), a, b):
                    classification = "co_occurrence_only"
                    explicit_matches = [match for sentence in re.split(r"(?<=[.!?])\s+|[\r\n]+", excerpt)
                                        for match in discovery_term_relationships._matches(sentence)]
                    if any({x.casefold(), y.casefold()} == {a.casefold(), b.casefold()}
                           for _, x, y in explicit_matches):
                        classification = "explicit_relationship"
                    elif re.search(r"\b(?:distinct|different|not the same|unrelated|separate)\b",
                                   excerpt, re.I):
                        classification = "possible_distinction"
                    evidence.append({
                        "citation": citation, "source": source, "kind": kind,
                        "event_time": when, "signal": classification,
                        "excerpt": excerpt.strip()[:380]})
                    if len(evidence) >= max_evidence:
                        break
                if len(evidence) >= max_evidence:
                    break
            signals = {x["signal"] for x in evidence}
            if "possible_distinction" in signals and "explicit_relationship" in signals:
                assessment = "conflicting_evidence"
            elif "possible_distinction" in signals:
                assessment = "possible_distinction"
            elif "explicit_relationship" in signals:
                assessment = "explicit_claim_needs_review"
            else:
                assessment = "unresolved"
            output.append(dict(item, assessment=assessment,
                               evidence=evidence, evidence_count=len(evidence),
                               status="candidate"))
        return {"pairs_generated": len(pairs), "evaluations": output,
                "method": "bounded_deterministic_evidence_triage"}
    finally:
        db.close()
