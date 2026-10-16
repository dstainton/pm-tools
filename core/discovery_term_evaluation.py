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
    # Discover name/code transitions by repeated, independent source references.
    # One side must already be a known concept or alias; the other is an
    # uppercase product-like code. Mere co-mention generates a review pair,
    # never an assertion of equivalence.
    known = defaultdict(dict)
    for cluster in clusters:
        scope = cluster["project"]
        for term in [cluster["canonical"]] + cluster["aliases"]:
            if len(term) >= 3:
                known[scope][term.casefold()] = term
    co_mentions = defaultdict(set)
    db = sqlite3.connect(str(db_path))
    try:
        discovery_fts._init(db)
        sql = "SELECT project, citation, title, body FROM discovery_fts_documents"
        args = []
        if project:
            sql += " WHERE project=?"
            args.append(project)
        for scope, citation, title, body in db.execute(sql, args):
            text = (title or "") + " " + (body or "")
            if len(text) > 25000:
                text = text[:25000]
            terms = known.get(scope, {})
            observed = [name for lower, name in terms.items() if
                        _phrase(text, name)]
            codes = set(re.findall(r"(?<![A-Za-z0-9])(?:[A-Z]{2,8}(?:\\s+[A-Z]{1,5}[0-9]{1,3})?|[A-Z]{2,6}[0-9]{1,3})(?![A-Za-z0-9])", text))
            for first in observed[:20]:
                for second in sorted(codes)[:30]:
                    if first.casefold() == second.casefold():
                        continue
                    key = (scope, first.casefold(), second.casefold())
                    co_mentions[key].add(citation)
        for (scope, first, second), refs in co_mentions.items():
            if len(refs) < 2:
                continue
            a, b = sorted((known[scope][first], second))
            key = (scope, a.casefold(), b.casefold())
            record = pairs.setdefault(key, {
                "project": scope, "a": a, "b": b,
                "basis": [], "source_citations": []})
            record["basis"].append("repeated_contextual_mention")
            record["source_citations"] = sorted(set(record["source_citations"]) | refs)
    finally:
        db.close()
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
            # Collect one passage per independent citation, favouring both-term
            # mentions. A repeated snippet from one comment is one source.
            candidates = []
            for citation, source, kind, when, title, body in db.execute(
                    sql, (item["project"],)):
                text = (title or "") + ". " + (body or "")
                if not (_phrase(text, a) or _phrase(text, b)):
                    continue
                spans = _passages(text, a, b)
                if not spans:
                    for term in (a, b):
                        hit = re.search(r"(?<!\\w)" + re.escape(term) + r"(?!\\w)", text, re.I)
                        if hit:
                            spans = [text[max(0, hit.start()-140):hit.end()+180]]
                            break
                excerpt = spans[0].strip()[:380]
                signal = "single_term_mention"
                if _phrase(excerpt, a) and _phrase(excerpt, b):
                    signal = "co_occurrence_only"
                    sentences = re.split(r"(?<=[.!?])\\s+|[\\r\\n]+", excerpt)
                    matches = [m for sentence in sentences
                               for m in discovery_term_relationships._matches(sentence)]
                    if any({x.casefold(), y.casefold()} == {a.casefold(), b.casefold()}
                           for _, x, y in matches):
                        signal = "explicit_relationship"
                    elif re.search(r"\\b(?:distinct|different|not the same|unrelated|separate)\\b",
                                   excerpt, re.I):
                        signal = "possible_distinction"
                candidates.append({
                    "citation": citation, "source": source, "kind": kind,
                    "event_time": when, "signal": signal, "excerpt": excerpt})
            priority = {"explicit_relationship": 0, "possible_distinction": 1,
                        "co_occurrence_only": 2, "single_term_mention": 3}
            candidates.sort(key=lambda x: (priority[x["signal"]],
                         x["event_time"] or "", x["citation"]))
            seen = set()
            for candidate in candidates:
                if candidate["citation"] not in seen:
                    seen.add(candidate["citation"])
                    evidence.append(candidate)
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
                               independent_sources=len(seen),
                               status="candidate"))
        return {"pairs_generated": len(pairs), "evaluations": output,
                "method": "bounded_deterministic_evidence_triage"}
    finally:
        db.close()
