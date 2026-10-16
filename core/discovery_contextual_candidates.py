"""Cited contextual relationship candidates, not asserted graph edges."""
import re
import sqlite3
from collections import defaultdict

from core import discovery_fts, discovery_concept_clusters

# These valid acronyms also appear as ordinary English words. An unqualified
# occurrence is not evidence of the named concept.
AMBIGUOUS_WORD_ACRONYMS = {"DID", "IT", "MAP", "CAN", "HAS", "MAY", "WILL",
                           "AS", "IN", "ON", "OR", "IF", "TO", "DO", "US"}

# Signals prioritize passages worth reviewing, not confirmed relationships.
RELATION_SIGNAL = re.compile(
    r"\b(?:integrat(?:es?|ed|ion)|depend(?:s|ed|ency)?|consum(?:es?|ed)|"
    r"provid(?:es?|ed)|deliver(?:s|ed)|part of|component of|"
    r"connect(?:s|ed)|replac(?:es?|ed)|formerly|renam(?:es?|ed)|"
    r"migrat(?:es?|ed|ion)|uses?|upstream|downstream|"
    r"calls?|exchang(?:es?|ed)|publish(?:es|ed)|mapping(?:s)?|"
    r"maps? to|glossary|onboard(?:ing|ed)?|verified by|"
    r"validated? against|source of truth)\b", re.I)



def candidates(db_path, project=None, limit=30):
    if limit < 1:
        raise ValueError("limit must be positive")
    clusters = discovery_concept_clusters.clusters(db_path, project=project, limit=None)
    terms = defaultdict(set)
    owners = defaultdict(set)
    for concept in clusters:
        identity = (concept["project"], concept["canonical"].casefold())
        for value in [concept["canonical"]] + concept["aliases"]:
            owners[(concept["project"], value.casefold())].add(identity)
            if (len(value) >= 3 and value.casefold() not in ("api", "aps", "bc")
                    and value.upper() not in AMBIGUOUS_WORD_ACRONYMS):
                terms[concept["project"]].add(value)
    ambiguous = {key for key, identities in owners.items() if len(identities) > 1}
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
                        if (owners[(scope, a.casefold())] &
                                owners[(scope, b.casefold())]):
                            continue
                        if ((scope, a.casefold()) in ambiguous or
                                (scope, b.casefold()) in ambiguous):
                            continue
                        key = (scope, a.casefold(), b.casefold())
                        obj = matches.setdefault(key, {
                            "project": scope, "from": a, "to": b, "type": "unresolved",
                            "status": "candidate", "evidence": []})
                        if citation not in {x["citation"] for x in obj["evidence"]}:
                            obj["evidence"].append({"citation": citation, "kind": kind,
                                "event_time": when, "excerpt": fragment.strip(),
                                "relationship_signal": bool(RELATION_SIGNAL.search(fragment))})
        output = list(matches.values())
        for item in output:
            # Prefer explicitly relational passages within the model evidence cap.
            # Preserve all source citations and never infer a relation here.
            item["evidence"].sort(key=lambda ev: (not ev.get("relationship_signal"),
                                                    ev["citation"]))
            item["independent_sources"] = len(item["evidence"])
            item["signal_sources"] = sum(bool(e.get("relationship_signal"))
                                         for e in item["evidence"])
        output.sort(key=lambda x: (-x["signal_sources"], -x["independent_sources"],
                                   x["from"], x["to"]))
        return output[:limit]
    finally:
        db.close()
