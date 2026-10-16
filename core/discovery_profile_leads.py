"""Source-linked profile evidence leads from the offline discovery index.

A mention can identify relevant documentation, but cannot establish product
ownership, goals, responsibilities, or current terminology. No model or live
network calls. These are review leads only.
"""
import re
import sqlite3
from collections import defaultdict

from core import discovery_fts

SIGNAL = re.compile(
    r"\b(?:purpose|goal|outcome|capabilit\w*|responsib\w*|"
    r"provid\w*|enabl\w*|support\w*|boundar\w*|scope|"
    r"service|product|integrat\w*|depend\w*|architect\w*)\b", re.I)


def build(db_path, cfg, project=None, per_entity=5):
    """Find potential starting points for human profile verification."""
    if per_entity < 1:
        raise ValueError("per_entity must be positive")
    entities = []
    for kind, entries in (("product", cfg.get("products") or []),
                          ("workstream", cfg.get("workstreams") or [])):
        for entry in entries:
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            entities.append({"kind": kind, "name": name,
                             "abbrev": entry.get("abbrev") or "",
                             "project": entry.get("project") or entry.get("jira_project"),
                             "leads": [], "documents_matched": 0})
    db = sqlite3.connect(str(db_path))
    try:
        discovery_fts._init(db)
        sql = "SELECT project, source, citation, title, body FROM discovery_fts_documents"
        args = ()
        if project:
            sql += " WHERE project=?"
            args = (project,)
        scores = defaultdict(dict)
        counts = defaultdict(set)
        docs_scanned = 0
        source_counts = defaultdict(int)
        for scope, source, cite, title, body in db.execute(sql, args):
            docs_scanned += 1
            source_counts[source] += 1
            # Only full names are used. Abbreviations such as APS can
            # accidentally refer to the organization rather than a product.
            for index, item in enumerate(entities):
                if item["project"] and scope and item["project"] != scope:
                    continue
                name = item["name"]
                matcher = re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)", re.I)
                if not (matcher.search(title or "") or matcher.search(body or "")):
                    continue
                counts[index].add(cite)
                sections = [title or ""] + re.split(r"(?<=[.!?])\s+|[\r\n]+", body or "")
                for passage in sections:
                    if not 25 <= len(passage) <= 700 or not matcher.search(passage):
                        continue
                    signals = len(SIGNAL.findall(passage))
                    if signals == 0:
                        continue
                    # These rankings help locate reading material. They are
                    # not probabilities or model confidence values.
                    rank = min(signals, 5) + (2 if source == "confluence" else 0)
                    if matcher.search(title or ""):
                        rank += 1
                    current = scores[index].get(cite)
                    candidate = {"citation": cite, "source": source,
                                 "excerpt": passage.strip()[:400],
                                 "signal_count": signals, "_rank": rank}
                    if current is None or current["_rank"] < rank:
                        scores[index][cite] = candidate
        for index, item in enumerate(entities):
            item["documents_matched"] = len(counts[index])
            selected = sorted(scores[index].values(),
                              key=lambda row: (-row["_rank"], row["citation"]))[:per_entity]
            for row in selected:
                row.pop("_rank")
            item["leads"] = selected
            item["review_state"] = "needs human verification"
        return {
            "indexed_documents_scanned": docs_scanned,
            "indexed_source_counts": dict(sorted(source_counts.items())),
            "entities": entities,
            "warning": "Mentions are navigation leads, not ownership, purpose, or boundary claims.",
        }
    finally:
        db.close()
