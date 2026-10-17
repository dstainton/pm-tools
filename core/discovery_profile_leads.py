"""Source-linked profile evidence leads from the offline discovery index.

A mention can identify relevant documentation, but cannot establish product
ownership, goals, responsibilities, or current terminology. No model or live
network calls. These are review leads only.
"""
import re
import sqlite3
from collections import defaultdict

from core import discovery_evidence_priority, discovery_fts

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
        sql = ("SELECT project, source, source_key, kind, citation, title, body "
               "FROM discovery_fts_documents")
        args = ()
        if project:
            sql += " WHERE project=?"
            args = (project,)
        scores = defaultdict(dict)
        # Unique parent documents, not independently indexed comment/change rows.
        counts = defaultdict(set)
        raw_counts = defaultdict(set)
        docs_scanned = 0
        source_counts = defaultdict(int)
        kind_counts = defaultdict(int)
        distinct_issues = set()
        for scope, source, source_key, kind, cite, title, body in db.execute(sql, args):
            docs_scanned += 1
            source_counts[source] += 1
            kind_counts[(source, kind)] += 1
            group = discovery_evidence_priority.parent_group(
                scope, source, kind, source_key, cite)
            if source == "jira" and kind in ("issue", "comment", "change"):
                distinct_issues.add(group)
            # Only full names are used. Abbreviations such as APS can
            # accidentally refer to the organization rather than a product.
            for index, item in enumerate(entities):
                if item["project"] and scope and item["project"] != scope:
                    continue
                name = item["name"]
                matcher = re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)", re.I)
                if not (matcher.search(title or "") or matcher.search(body or "")):
                    continue
                counts[index].add(group)
                raw_counts[index].add(cite)
                sections = [title or ""] + re.split(r"(?<=[.!?])\s+|[\r\n]+", body or "")
                for passage in sections:
                    if not 25 <= len(passage) <= 700 or not matcher.search(passage):
                        continue
                    signals = len(SIGNAL.findall(passage))
                    if signals == 0:
                        continue
                    # These rankings help locate reading material. They are
                    # not probabilities or model confidence values.
                    # Current descriptive pages outrank issue descriptions;
                    # comments only supplement them; historical changes are
                    # retained but cannot crowd out stronger parent evidence.
                    tier = discovery_evidence_priority.priority(source, kind)
                    title_hit = bool(matcher.search(title or ""))
                    score = (tier, -int(title_hit), -min(signals, 5), cite)
                    current = scores[index].get(group)
                    candidate = {"citation": cite, "source": source, "kind": kind,
                                 "excerpt": passage.strip()[:400],
                                 "signal_count": signals, "_rank": score}
                    if current is None or candidate["_rank"] < current["_rank"]:
                        scores[index][group] = candidate
        for index, item in enumerate(entities):
            item["documents_matched"] = len(counts[index])
            item["evidence_records_matched"] = len(raw_counts[index])
            selected = sorted(scores[index].values(),
                              key=lambda row: row["_rank"])[:per_entity]
            for row in selected:
                row.pop("_rank")
            item["leads"] = selected
            item["review_state"] = "needs human verification"
        return {
            "indexed_documents_scanned": docs_scanned,
            "indexed_source_counts": dict(sorted(source_counts.items())),
            "indexed_kind_counts": {
                "{}:{}".format(source, kind): count
                for (source, kind), count in sorted(kind_counts.items())},
            "jira_unique_issues": len(distinct_issues),
            "jira_supporting_records": sum(
                v for (source, kind), v in kind_counts.items()
                if source == "jira" and kind in ("comment", "change")),
            "entities": entities,
            "warning": "Mentions are navigation leads, not ownership, purpose, or boundary claims.",
        }
    finally:
        db.close()
