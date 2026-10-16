"""Cited contextual relationship candidates, not asserted graph edges."""
import re
import sqlite3
from collections import defaultdict

from core import discovery_fts, discovery_concept_clusters


def candidates(db_path, project=None, limit=30):
    if limit < 1:
        raise ValueError("limit must be positive")
    clusters = discovery_concept_clusters.clusters(db_path, project=project, limit=None)
    terms = defaultdict(set)
    for concept in clusters:
        for value in [concept["canonical"]] + concept["aliases"]:
            if len(value) >= 3 and value.casefold() not in ("api", "aps", "bc"):
                terms[concept["project"]].add(value)
    matches = {}
    db = sqlite3.connect(str(db_path))
    try:
        discovery_fts._init(db)
        sql = "SELECT project, citation, kind, event_time, title, body FROM discovery_fts_documents"
        args = ()
        if project:
            sql += " WHERE project=?"
            args = (project,)
        for scope, citation, kind, when, title, body in db.execute(sql, args):
            for fragment in [title or ""] + re.split(r"(?<=[.!?])\s+|[\r\n]+", body or ""):
                if not 15 <= len(fragment) <= 450:
                    continue
                hits = [term for term in terms.get(scope, ())
                        if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", fragment, re.I)]
                if len(hits) < 2 or len(hits) > 6:
                    continue
                # Candidate generation does not infer that co-mentions imply any relation.
                for i, a in enumerate(sorted(hits)):
                    for b in sorted(hits)[i + 1:]:
                        if a.casefold() == b.casefold():
                            continue
                        key = (scope, a.casefold(), b.casefold())
                        obj = matches.setdefault(key, {
                            "project": scope, "from": a, "to": b, "type": "unresolved",
                            "status": "candidate", "evidence": []})
                        if citation not in {x["citation"] for x in obj["evidence"]}:
                            obj["evidence"].append({"citation": citation, "kind": kind,
                                "event_time": when, "excerpt": fragment.strip()})
        output = list(matches.values())
        for item in output:
            item["independent_sources"] = len(item["evidence"])
        output.sort(key=lambda x: (-x["independent_sources"], x["from"], x["to"]))
        return output[:limit]
    finally:
        db.close()
