"""Build substantial, citation-preserving evidence packs from the local index.

Unlike the initial discovery snippets, these packs include surrounding prose and
multiple sections of long documents. They never fetch remote sources, include
unpublished drafts, or turn Jira change history into current-state evidence.
The caller chooses the character budget to match its local model's real context.
"""
import re
import sqlite3

from core import discovery_evidence_priority, discovery_fts

DEFAULT_CONTEXT_CHARS = 80000
DEFAULT_CONTEXT_DOCUMENTS = 24
MAX_CONTEXT_CHARS = 400000
RELATION = re.compile(
    r"\b(?:depends?|integrates?|provides?|consumes?|requires?|"
    r"part of|belongs to|responsib\w*|owned by|used by|"
    r"validates?|replaces?|formerly|publishes?|onboards?|"
    r"boundar\w*|capabilit\w*|purpose|scope|architecture)\b", re.I)


def _check_budget(max_chars, max_documents):
    if not isinstance(max_chars, int) or not 4000 <= max_chars <= MAX_CONTEXT_CHARS:
        raise ValueError("Context characters must be 4,000..400,000")
    if not isinstance(max_documents, int) or not 1 <= max_documents <= 100:
        raise ValueError("Context documents must be 1..100")


def _terms(names):
    return [str(name).strip() for name in names if str(name or "").strip()]


def _hit_regex(term):
    return re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.I)


def _window_text(body, terms, max_chars):
    """Extract several broad nearby sections, not only a one-sentence mention.

    Indexed Confluence HTML was flattened to a single line. Use overlap-aware
    character windows around literal concept mentions; don't pretend that a
    synthetic window is an original Confluence paragraph or section heading.
    """
    body = str(body or "")
    if len(body) <= max_chars:
        return body
    expressions = [_hit_regex(t) for t in terms]
    candidates = []
    for term_index, pattern in enumerate(expressions):
        for match in list(pattern.finditer(body))[:50]:
            start = max(0, match.start() - 1500)
            end = min(len(body), match.end() + 2300)
            block = body[start:end]
            matched = sum(bool(e.search(block)) for e in expressions)
            score = (matched * 10 + min(6, len(RELATION.findall(block))),
                     -start, term_index)
            candidates.append((score, start, end))
    if not candidates:
        return body[:max_chars]
    # Include context for terms that may appear in entirely different sections.
    candidates.sort(key=lambda entry: entry[0], reverse=True)
    selected = []
    coverage = set()
    for _, start, end in candidates:
        text = body[start:end]
        hits = {i for i, expr in enumerate(expressions) if expr.search(text)}
        if not hits - coverage:
            continue
        if any(start < prior_end and end > prior_start
               for prior_start, prior_end in selected):
            continue
        selected.append((start, end))
        coverage.update(hits)
        if len(coverage) == len(expressions):
            break
    for _, start, end in candidates:
        if any(start < prior_end and end > prior_start
               for prior_start, prior_end in selected):
            continue
        selected.append((start, end))
        if len(selected) >= 15:
            break
    # Preserve original document sequence so content remains coherent.
    selected.sort()
    pieces = []
    used = 0
    for start, end in selected:
        budget = max_chars - used
        if budget < 180:
            break
        separator = "\n[Earlier/later portions omitted]\n" if pieces else ""
        available = budget - len(separator)
        if available <= 0:
            break
        piece = body[start:min(end, start + available)]
        pieces.append(separator + piece)
        used += len(separator) + len(piece)
    return "".join(pieces) if pieces else body[:max_chars]


def _lookup(db, project, citations, terms, max_found):
    """Combine cited source records with fresh FTS search for entire documents."""
    rows = {}
    columns = "d.source, d.kind, d.source_key, d.citation, d.title, d.body, d.event_time"
    if citations:
        identifiers = sorted(set(citations))
        for start in range(0, len(identifiers), 250):
            batch = identifiers[start:start + 250]
            ph = ",".join("?" for _ in batch)
            sql = ("SELECT source,kind,source_key,citation,title,body,event_time "
                   "FROM discovery_fts_documents WHERE project=? AND citation IN (" +
                   ph + ")")
            for row in db.execute(sql, (project, *batch)):
                rows.setdefault(row[3], row)
    # Full document retrieval, including relevant pages where concepts appear
    # in different paragraphs and would not be a contextual-candidate pair.
    if terms:
        clauses = []
        for term in terms:
            clauses.append('"' + term.replace('"', '""') + '"')
        for query in (" AND ".join(clauses), *clauses):
            sql = (
                "SELECT " + columns +
                " FROM discovery_fts JOIN discovery_fts_documents d ON discovery_fts.doc_id=d.doc_id "
                "WHERE discovery_fts MATCH ? AND d.project=? "
                "AND ((d.source='confluence' AND d.kind IN "
                "('confluence_page','confluence_blogpost','confluence_blog')) "
                "OR (d.source='jira' AND d.kind='issue')) "
                "ORDER BY bm25(discovery_fts) LIMIT ?")
            try:
                for row in db.execute(sql, (query, project, max_found)):
                    rows.setdefault(row[3], row)
            except sqlite3.OperationalError as exc:
                # Missing term in an index is normal, but schema/FTS failures
                # must not be silently interpreted as no evidence.
                if "fts5" not in str(exc).lower() and "syntax" not in str(exc).lower():
                    raise
    # If a cited comment is found, load its parent Jira issue as context.
    for row in list(rows.values()):
        source, kind, key, citation = row[:4]
        if source != "jira" or kind != "comment" or not key:
            continue
        parent = db.execute(
            "SELECT source,kind,source_key,citation,title,body,event_time "
            "FROM discovery_fts_documents WHERE project=? AND "
            "source='jira' AND kind='issue' AND source_key=? LIMIT 1",
            (project, key)).fetchone()
        if parent:
            rows.setdefault(parent[3], parent)
    return list(rows.values())


def build(db_path, project, terms, citations=(), max_chars=DEFAULT_CONTEXT_CHARS,
          max_documents=DEFAULT_CONTEXT_DOCUMENTS):
    """Return source-labelled substantial excerpts respecting a hard body cap."""
    _check_budget(max_chars, max_documents)
    if not project:
        raise ValueError("Project scope is required for source context")
    names = _terms(terms)
    seeds = {str(c) for c in citations if c}
    db = sqlite3.connect(str(db_path))
    try:
        discovery_fts._init(db)
        raw = _lookup(db, project, seeds, names, max_documents * 6)
    finally:
        db.close()
    eligible = []
    for source, kind, key, citation, title, body, when in raw:
        if discovery_evidence_priority.is_historical(source, kind):
            continue
        if source == "confluence" and kind not in (
                "confluence_page", "confluence_blogpost", "confluence_blog",
                "confluence_comment"):
            continue
        if source == "jira" and kind not in ("issue", "comment"):
            continue
        if citation not in seeds and (source == "jira" and kind != "issue" or
                                     source == "confluence" and kind == "confluence_comment"):
            continue
        expressions = [_hit_regex(term) for term in names]
        body = str(body or "")
        title = str(title or "")
        found = sum(bool(expr.search(body) or expr.search(title)) for expr in expressions)
        if citation not in seeds and not found:
            continue
        priority = discovery_evidence_priority.priority(source, kind)
        signals = min(12, len(RELATION.findall(body[:35000])))
        # Preserve evidence that originally motivated this proposal before
        # broader FTS hits. Then favour published source authority and clarity.
        score = (0 if citation in seeds else 1, priority, -found, -signals,
                 citation)
        eligible.append((score, (source, kind, key, citation, title, body, when)))
    eligible.sort(key=lambda item: item[0])
    eligible = eligible[:max_documents]
    selected = []
    remaining = max_chars
    # Reserve capacity for several independent documents and large sections.
    # Add each source once, and never count the same issue's comments as
    # independent validation of its own issue.
    per_source = min(12000, max(2400, max_chars // min(max(1, len(eligible)), 10)))
    for _, (source, kind, key, citation, title, body, when) in eligible:
        if remaining < 150:
            break
        allowance = min(per_source, remaining)
        excerpt = _window_text(body, names, allowance)
        if not excerpt:
            continue
        selected.append({
            "citation": citation, "source": source, "kind": kind,
            "title": title[:300], "date": when,
            "excerpt": excerpt})
        remaining -= len(excerpt)
    return {
        "evidence": selected, "project": project,
        "characters": max_chars - remaining,
        "documents": len(selected),
        "truncated": len(eligible) > len(selected) or bool(
            any(len(str(row[1][5] or "")) > per_source for row in eligible)),
        "context_limit": max_chars,
        "document_limit": max_documents,
        "citations": [item["citation"] for item in selected],
        "method": "offline_published_full_document_context",
    }
