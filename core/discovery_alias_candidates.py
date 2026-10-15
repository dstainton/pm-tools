"""Conservative, read-only acronym candidate discovery from source text.

A co-located abbreviation is a *candidate*, not established equivalence.
Matches are scoped to their original Jira project and retain citations.
"""
import re
import sqlite3

from core import discovery_concepts

PAIR = re.compile(r"(?P<name>[A-Za-z][A-Za-z0-9&/-]*(?:\s+[A-Za-z][A-Za-z0-9&/-]*){1,6})\s*\((?P<abbr>[A-Z][A-Z0-9]{1,9})\)")


def _align(short, long):
    """Schwartz-Hearst-style backward character alignment.

    The first short-form character must match the start of the long form.
    This detects non-initial-letter abbreviations without using an LLM.
    """
    i = len(short) - 1
    j = len(long) - 1
    while i >= 0:
        char = short[i].casefold()
        while j >= 0:
            if long[j].casefold() == char and (i != 0 or j == 0 or not long[j - 1].isalnum()):
                break
            j -= 1
        if j < 0:
            return False
        i -= 1
        j -= 1
    return True


def _definition(short, words):
    """Find the shortest trailing word span with valid alignment."""
    for count in range(2, min(len(words), len(short) + 5) + 1):
        phrase = " ".join(words[-count:])
        if _align(short, phrase):
            return phrase
    return None


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
                    name = _definition(abbreviation, words)
                    if name is None:
                        continue
                    key = (scope, name.casefold(), abbreviation)
                    record = found.setdefault(key, {
                        "project": scope, "canonical": name, "alias": abbreviation,
                        "relation": "abbreviation", "status": "candidate",
                        "alignment": "schwartz-hearst",
                        "citations": []})
                    if citation not in record["citations"]:
                        record["citations"].append(citation)
        return sorted(found.values(), key=lambda x: (
            -len(x["citations"]), x["project"] or "", x["canonical"]))[:limit]
    finally:
        db.close()


def stage(db_path, project=None, limit=50):
    """Record candidate aliases without promoting either side to confirmed."""
    records = candidates(db_path, project, limit)
    with sqlite3.connect(str(db_path)) as db:
        discovery_concepts._init(db)
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
