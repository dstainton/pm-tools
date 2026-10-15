"""Evidence-backed concept/alias registry for deterministic, scoped retrieval.

Aliases must be explicitly confirmed before they expand search. Candidates may
be recorded for review but never become organization-wide synonyms by default.
"""
import json
import sqlite3


def _init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS discovery_concepts (
        concept_id TEXT PRIMARY KEY, canonical TEXT NOT NULL,
        project TEXT, status TEXT NOT NULL CHECK(status IN ('candidate','confirmed'))
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS discovery_aliases (
        concept_id TEXT NOT NULL, alias TEXT NOT NULL,
        relation TEXT NOT NULL CHECK(relation IN ('abbreviation','historical_name','alternate_name')),
        status TEXT NOT NULL CHECK(status IN ('candidate','confirmed')),
        citation TEXT NOT NULL, effective_from TEXT, effective_to TEXT,
        PRIMARY KEY(concept_id, alias, citation),
        FOREIGN KEY(concept_id) REFERENCES discovery_concepts(concept_id)
    )""")
    db.commit()


def register(db_path, concept_id, canonical, project=None, status="candidate"):
    if not concept_id.strip() or not canonical.strip():
        raise ValueError("Concept ID and canonical term required")
    db = sqlite3.connect(str(db_path))
    try:
        db.execute("PRAGMA foreign_keys=ON")
        _init(db)
        with db:
            db.execute("""INSERT INTO discovery_concepts
                (concept_id, canonical, project, status) VALUES (?, ?, ?, ?)
                ON CONFLICT(concept_id) DO UPDATE SET canonical=excluded.canonical,
                    project=excluded.project, status=excluded.status""",
                (concept_id, canonical, project, status))
    finally:
        db.close()


def alias(db_path, concept_id, term, relation, citation,
          status="candidate", effective_from=None, effective_to=None):
    if not term.strip() or not citation.strip():
        raise ValueError("Alias and source citation required")
    if relation not in ("abbreviation", "historical_name", "alternate_name"):
        raise ValueError("Unsupported relationship")
    if status not in ("candidate", "confirmed"):
        raise ValueError("Status must be candidate or confirmed")
    db = sqlite3.connect(str(db_path))
    try:
        db.execute("PRAGMA foreign_keys=ON")
        _init(db)
        with db:
            db.execute("""INSERT INTO discovery_aliases
                (concept_id, alias, relation, status, citation, effective_from, effective_to)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(concept_id, alias, citation) DO UPDATE SET
                relation=excluded.relation, status=excluded.status,
                effective_from=excluded.effective_from, effective_to=excluded.effective_to""",
                (concept_id, term, relation, status, citation,
                 effective_from, effective_to))
    finally:
        db.close()


def expansions(db_path, query, project=None):
    """Return confirmed aliases only for an exact canonical/alias lookup."""
    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row
    try:
        _init(db)
        sql = """SELECT DISTINCT c.concept_id, c.canonical, c.project,
                        a.alias, a.relation, a.citation, a.effective_from, a.effective_to
                 FROM discovery_concepts c JOIN discovery_aliases a
                   ON a.concept_id=c.concept_id
                 WHERE c.status='confirmed' AND a.status='confirmed'
                   AND (lower(c.canonical)=lower(?) OR EXISTS (
                      SELECT 1 FROM discovery_aliases matched
                      WHERE matched.concept_id=c.concept_id
                        AND matched.status='confirmed'
                        AND lower(matched.alias)=lower(?)))
                   AND (c.project IS NULL OR c.project=?)"""
        return [dict(row) for row in db.execute(sql, (query, query, project))]
    finally:
        db.close()
