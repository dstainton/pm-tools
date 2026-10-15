"""Deterministic candidate terminology clustering, without assumed ownership.

Names are grouped only when their normalized forms agree within the same
source scope. A shared abbreviation by itself never merges concepts.
"""
import re
import sqlite3
from collections import defaultdict

from core import discovery_concepts


def normalize(text):
    """Conservative spelling, spacing and case normalization for comparison."""
    value = re.sub(r"\bprogramme(s)?\b", lambda m: "program" + (m.group(1) or ""),
                   str(text or ""), flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def clusters(db_path, project=None, limit=100):
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row
    try:
        discovery_concepts._init(db)
        sql = """SELECT c.concept_id, c.canonical, c.project,
                        c.status AS concept_status, a.alias, a.relation,
                        a.status AS alias_status, a.citation
                 FROM discovery_concepts c JOIN discovery_aliases a
                 ON c.concept_id = a.concept_id"""
        args = []
        if project:
            sql += " WHERE c.project=?"
            args.append(project)
        rows = db.execute(sql, args)
        grouped = {}
        for r in rows:
            key = (r["project"], normalize(r["canonical"]))
            group = grouped.setdefault(key, {
                "project": r["project"], "normalized": key[1],
                "names": set(), "concept_ids": set(), "aliases": defaultdict(set),
                "citations": set(), "statuses": set(), "relationships": set()})
            group["names"].add(r["canonical"])
            group["concept_ids"].add(r["concept_id"])
            group["aliases"][r["alias"]].add(r["citation"])
            group["citations"].add(r["citation"])
            group["statuses"].add((r["concept_status"], r["alias_status"]))
            group["relationships"].add(r["relation"])
        alias_meanings = defaultdict(set)
        for key, group in grouped.items():
            for alias in group["aliases"]:
                alias_meanings[(group["project"], normalize(alias))].add(key)
        result = []
        for key, group in grouped.items():
            ambiguous = sorted(alias for alias in group["aliases"]
                               if len(alias_meanings[(group["project"],
                                                      normalize(alias))]) > 1)
            result.append({
                "project": group["project"], "canonical": sorted(
                    group["names"], key=lambda n: (len(n), n.casefold()))[0],
                "variants": sorted(group["names"]),
                "aliases": sorted(group["aliases"]),
                "citations": sorted(group["citations"]),
                "evidence_count": len(group["citations"]),
                "ambiguous_aliases": ambiguous,
                "concept_ids": sorted(group["concept_ids"]),
                "review_status": "candidate" if any(
                    a != "confirmed" or b != "confirmed"
                    for a, b in group["statuses"]) else "confirmed",
                "relationships": sorted(group["relationships"]),
            })
        result.sort(key=lambda r: (
            -r["evidence_count"], r["project"] or "", r["canonical"].casefold()))
        return result if limit is None else result[:limit]
    finally:
        db.close()
