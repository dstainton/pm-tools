"""Conservative, read-only acronym candidate discovery from source text.

A co-located abbreviation is a *candidate*, not established equivalence.
Matches are scoped to their original Jira project and retain citations.
"""
import re
import sqlite3

from core import discovery_concepts

PAIR = re.compile(r"(?P<name>[A-Za-z][A-Za-z0-9&/-]*(?:\s+[A-Za-z][A-Za-z0-9&/-]*){1,6})\s*\((?P<abbr>[A-Z][A-Z0-9]{1,9})\)")


def _initials(words):
    return "".join(word[0].upper() for word in re.findall(r"[A-Za-z]+", words))


def candidates(db_path, project=None, limit=50):
    """Mine explicit 'Expanded Name (ABC)' evidence without writes."""
    if limit < 1 or limit > 500:
        raise ValueError("limit must be 1..500")
    db = sqlite3.connect(str(db_path))
    try:
        sql = """SELECT citation, project, title, body FROM discovery_fts_documents
                 WHERE kind IN ('issue', 'comment')"""
        args = []
        if project:
            sql += " AND project=?"
            args.append(project)
        sql += " ORDER BY citation"
        found = {}
        for citation, scope, title, body in db.execute(sql, args):
            for text in (title, body):
                for match in PAIR.finditer(text):
                    abbreviation = match.group("abbr")
                    raw = match.group("name")
                    words = raw.split()
                    # Take only the trailing number of words matching the
                    # abbreviation length; avoids absorbing sentence context.
                    words = words[-len(abbreviation):]
                    name = " ".join(words)
                    if len(words) < 2:
                        continue
                    exact_initials = _initials(name) == abbreviation
                    if not exact_initials and name[0].upper() != abbreviation[0]:
                        continue
                    key = (scope, name.casefold(), abbreviation)
                    record = found.setdefault(key, {
                        "project": scope, "canonical": name, "alias": abbreviation,
                        "relation": "abbreviation", "status": "candidate",
                        "initials_match": exact_initials, "citations": []})
                    if citation not in record["citations"]:
                        record["citations"].append(citation)
        # A non-initialism abbreviation needs corroboration from at least
        # two distinct cited records; neither category is ever auto-approved.
        qualified = [x for x in found.values() if x["initials_match"] or
                     len(x["citations"]) >= 2]
        return sorted(qualified, key=lambda x: (
            -len(x["citations"]), x["project"] or "", x["canonical"]))[:limit]
    finally:
        db.close()


def stage(db_path, project=None, limit=50):
    """Record candidate aliases without promoting either side to confirmed."""
    records = candidates(db_path, project, limit)
    for entry in records:
        import hashlib
        concept_id = "auto:" + hashlib.sha256(
            (str(entry["project"]) + ":" + entry["canonical"].casefold()).encode()
        ).hexdigest()[:20]
        with sqlite3.connect(str(db_path)) as db:
            existing = db.execute("SELECT status FROM discovery_concepts WHERE concept_id=?",
                                  (concept_id,)).fetchone()
        if existing and existing[0] == "confirmed":
            continue
        discovery_concepts.register(db_path, concept_id, entry["canonical"],
                                    project=entry["project"], status="candidate")
        for citation in entry["citations"]:
            discovery_concepts.alias(db_path, concept_id, entry["alias"],
                                     "abbreviation", citation, status="candidate")
    return records
