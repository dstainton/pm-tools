"""Deterministic, offline, source-cited FTS5 index of locally collected Jira evidence.

The source SQLite tables are immutable to this module. Index documents are
observations, not verified product names or decisions. Re-running is idempotent.
"""
import hashlib
import json
import sqlite3


def _plain(value):
    """Extract text from Jira plain strings or Atlassian Document Format."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(filter(None, (_plain(item) for item in value)))
    if isinstance(value, dict):
        parts = []
        if value.get("type") == "text" and isinstance(value.get("text"), str):
            parts.append(value["text"])
        for field in ("content", "body"):
            if field in value:
                parts.append(_plain(value[field]))
        return " ".join(filter(None, parts))
    return ""


def _init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS discovery_fts_documents (
        doc_id TEXT PRIMARY KEY, source TEXT NOT NULL,
        source_key TEXT NOT NULL, project TEXT,
        kind TEXT NOT NULL, event_time TEXT, updated_at TEXT,
        citation TEXT NOT NULL, digest TEXT NOT NULL,
        title TEXT NOT NULL, body TEXT NOT NULL)""")
    db.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS discovery_fts
        USING fts5(doc_id UNINDEXED, title, body, tokenize='unicode61')""")
    db.commit()


def _put(db, doc_id, source_key, project, kind, event_time, updated_at,
         title, body, citation, source="jira"):
    digest = hashlib.sha256(json.dumps(
        [project, kind, event_time, updated_at, title, body, citation],
        ensure_ascii=False).encode("utf-8")).hexdigest()
    old = db.execute("SELECT digest FROM discovery_fts_documents WHERE doc_id=?",
                     (doc_id,)).fetchone()
    if old and old[0] == digest:
        return False
    if old:
        db.execute("DELETE FROM discovery_fts WHERE doc_id=?", (doc_id,))
    db.execute("""INSERT OR REPLACE INTO discovery_fts_documents
        (doc_id, source, source_key, project, kind, event_time, updated_at,
         citation, digest, title, body)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (doc_id, source, source_key, project, kind, event_time, updated_at,
         citation, digest, title, body))
    db.execute("INSERT INTO discovery_fts(doc_id, title, body) VALUES (?, ?, ?)",
               (doc_id, title, body))
    return True


def index_jira(db_path, on_progress=None):
    """Index retained issue, comment and change records without network calls."""
    db = sqlite3.connect(str(db_path))
    try:
        _init(db)
        names = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "jira_raw_issues" not in names:
            raise ValueError("Run Jira inventory before building the evidence index")
        rows = db.execute(
            "SELECT project, issue_key, payload FROM jira_raw_issues ORDER BY project, issue_key")
        processed = updated = 0
        with db:
            for project, key, raw in rows:
                issue = json.loads(raw)
                fields = issue.get("fields") or {}
                title = str(fields.get("summary") or key)
                components = [str(x.get("name") or "") for x in fields.get("components") or []
                              if isinstance(x, dict)]
                labels = [str(x) for x in fields.get("labels") or []]
                parent = (fields.get("parent") or {}).get("key") or ""
                body = " ".join(filter(None, [
                    _plain(fields.get("description")), " ".join(components),
                    " ".join(labels), str(parent),
                    str((fields.get("issuetype") or {}).get("name") or "")]))
                updated += int(_put(db, "jira:issue:" + key, key, project, "issue",
                    fields.get("created"), fields.get("updated"), title, body,
                    "jira:" + key))
                processed += 1
                if on_progress and processed % 100 == 0:
                    on_progress(processed)
            if "jira_comments" in names:
                for key, comment_id, payload in db.execute(
                        "SELECT issue_key, comment_id, payload FROM jira_comments"):
                    comment = json.loads(payload)
                    updated += int(_put(db, "jira:comment:" + key + ":" + comment_id,
                        key, key.split("-")[0], "comment", comment.get("created"),
                        comment.get("updated"), key + " comment " + comment_id,
                        _plain(comment.get("body")), "jira:" + key + "#comment-" + comment_id))
            if "jira_history_events" in names:
                for key, history_id, field, before, after, when in db.execute(
                        """SELECT issue_key, history_id, field_name, old_value,
                                  new_value, event_time FROM jira_history_events"""):
                    updated += int(_put(db, "jira:change:" + key + ":" + history_id,
                        key, key.split("-")[0], "change", when, None,
                        key + " " + str(field), "Changed from {} to {}".format(
                            before or "", after or ""),
                        "jira:" + key + "#changelog-" + history_id))
        return {"issues_processed": processed, "documents_updated": updated,
                "documents_total": db.execute(
                    "SELECT COUNT(*) FROM discovery_fts_documents").fetchone()[0]}
    finally:
        db.close()


def search(db_path, query, limit=20, project=None, kind=None):
    if not str(query or "").strip():
        raise ValueError("Search query must not be empty")
    if limit < 1 or limit > 100:
        raise ValueError("Search limit must be 1..100")
    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row
    try:
        _init(db)
        sql = """SELECT d.source_key, d.project, d.kind, d.event_time,
                        d.citation, d.title, snippet(discovery_fts, 2, '[', ']', ' … ', 18)
                        AS excerpt, bm25(discovery_fts) AS score
                 FROM discovery_fts JOIN discovery_fts_documents d
                 ON d.doc_id=discovery_fts.doc_id
                 WHERE discovery_fts MATCH ?"""
        params = [query]
        if project:
            sql += " AND d.project=?"
            params.append(project)
        if kind:
            sql += " AND d.kind=?"
            params.append(kind)
        sql += " ORDER BY score, d.doc_id LIMIT ?"
        params.append(limit)
        return [dict(row) for row in db.execute(sql, params)]
    finally:
        db.close()
