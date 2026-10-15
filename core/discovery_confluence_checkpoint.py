"""Checkpointed, bounded Confluence page inventory respecting configured scope.

This collector is independent of the older capped metadata report. Every run
continues at a persisted CQL offset; the current scope is bound to a fingerprint
of the authorized root and space. No content is downloaded or modified.
"""
import hashlib
import json
import sqlite3

from core import discovery_inventory, sources


def _init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS confluence_inventory_cursor (
        scope_id TEXT PRIMARY KEY, scope_json TEXT NOT NULL,
        offset INTEGER NOT NULL, status TEXT NOT NULL, error TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS confluence_inventory_items (
        scope_id TEXT NOT NULL, content_id TEXT NOT NULL, space TEXT,
        title TEXT, content_type TEXT, updated TEXT, ancestors TEXT,
        PRIMARY KEY(scope_id, content_id))""")
    db.commit()


def _identity(scope):
    key = json.dumps(scope, sort_keys=True)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def crawl(cfg, db_path, max_rows=100, on_progress=None):
    """Collect at most max_rows search results per scope, resuming next time."""
    if max_rows < 1:
        raise ValueError("max_rows must be positive")
    scopes = discovery_inventory._scopes(cfg)
    db = sqlite3.connect(str(db_path))
    results = []
    def emit(scope, status, offset, processed, index, total):
        if on_progress is not None:
            name = ("Space " + str(scope.get("space") or "unknown")
                    if scope.get("type") == "space"
                    else "Page tree " + str(scope.get("root_title") or scope.get("root_id") or "unknown"))
            on_progress({"name": name, "status": status, "offset": offset,
                         "processed": processed, "index": index, "total": total})
    try:
        _init(db)
        for scope_index, configured in enumerate(scopes, 1):
            # Resolve title-based roots before generating the checkpoint ID.
            entry = {"scope": configured, "status": "unavailable", "processed": 0}
            results.append(entry)
            try:
                resolved = discovery_inventory._resolve(cfg, configured)
                scope, root = resolved if isinstance(resolved, tuple) else (resolved, None)
                sid = _identity(scope)
                record = db.execute(
                    "SELECT offset, status FROM confluence_inventory_cursor WHERE scope_id=?",
                    (sid,)).fetchone()
                offset, status = record if record else (0, "pending")
                if status == "complete":
                    entry.update(status="complete", offset=offset, scope=scope)
                    emit(scope, "complete", offset, 0, scope_index, len(scopes))
                    continue
                emit(scope, "collecting", offset, 0, scope_index, len(scopes))
                if root:
                    with db:
                        db.execute("""INSERT OR IGNORE INTO confluence_inventory_items
                            (scope_id,content_id,space,title,content_type,updated,ancestors)
                            VALUES(?,?,?,?,?,?,?)""", (
                                sid, str(root["id"]), scope.get("space"),
                                root.get("title") or "", root.get("type") or "page",
                                (root.get("version") or {}).get("when"),
                                json.dumps([])))
                remaining = max_rows
                while remaining:
                    rows, more = sources.list_confluence_inventory(
                        cfg, scope.get("space"), start=offset,
                        limit=min(25, remaining),
                        ancestor_id=scope["root_id"] if scope["type"] == "page_tree" else None)
                    if not rows and more:
                        raise ValueError("Empty search page despite continuation")
                    for row in rows:
                        ancestors = [str(a.get("id")) for a in (row.get("ancestors") or [])
                                     if isinstance(a, dict) and a.get("id")]
                        if (scope["type"] == "page_tree" and
                                scope["root_id"] not in ancestors and
                                str(row.get("id")) != scope["root_id"]):
                            continue
                        if not row.get("id"):
                            continue
                        with db:
                            db.execute("""INSERT OR REPLACE INTO confluence_inventory_items
                              (scope_id,content_id,space,title,content_type,updated,ancestors)
                              VALUES(?,?,?,?,?,?,?)""", (
                                sid, str(row["id"]), scope.get("space"),
                                row.get("title") or "", row.get("type") or "page",
                                (row.get("version") or {}).get("when"),
                                json.dumps(ancestors)))
                    offset += len(rows)
                    remaining -= len(rows)
                    status = "complete" if not more else "incomplete"
                    with db:
                        db.execute("""INSERT INTO confluence_inventory_cursor
                          (scope_id,scope_json,offset,status,error) VALUES(?,?,?,?,NULL)
                          ON CONFLICT(scope_id) DO UPDATE SET
                          offset=excluded.offset,status=excluded.status,error=NULL""",
                          (sid, json.dumps(scope, sort_keys=True), offset, status))
                    entry["processed"] += len(rows)
                    emit(scope, "complete" if not more else "collecting",
                         offset, entry["processed"], scope_index, len(scopes))
                    if not more:
                        break
                    if not rows:
                        raise ValueError("No pagination progress")
                entry.update(scope=scope, offset=offset, status=status)
            except Exception as exc:
                entry.update(status="incomplete", error="{}: {}".format(
                    type(exc).__name__, str(exc)[:160]))
                emit(entry.get("scope", configured), "incomplete",
                     entry.get("offset", 0), entry["processed"],
                     scope_index, len(scopes))
        return results
    finally:
        db.close()

def indexed_inventory(cfg, db_path):
    """Read only checkpoint entries belonging to currently authorized scopes.

    Does not perform network requests or expand a page tree to an entire space.
    Missing/incomplete checkpoints prevent a complete-coverage claim.
    """
    db = sqlite3.connect(str(db_path))
    try:
        _init(db)
        pages = {}
        statuses = []
        for configured in discovery_inventory._scopes(cfg):
            # Title-based roots are resolved during crawl. Match the persisted
            # configured scope by its resolved identity; do not guess identities.
            matches = []
            for sid, scope_json, status, offset in db.execute(
                    "SELECT scope_id, scope_json, status, offset FROM confluence_inventory_cursor"):
                scope = json.loads(scope_json)
                if scope["type"] != configured["type"]:
                    continue
                if configured.get("space") and configured["space"] != scope.get("space"):
                    continue
                if configured["type"] == "page_tree":
                    root = configured.get("root_id")
                    title = configured.get("root_title")
                    if root and root != scope.get("root_id"):
                        continue
                    if title and title != scope.get("root_title"):
                        continue
                matches.append((sid, status, offset))
            if len(matches) != 1:
                statuses.append({"scope": configured, "status": "unavailable",
                                 "detail": "No unique checkpoint for this authorized scope"})
                continue
            sid, status, offset = matches[0]
            statuses.append({"scope": configured, "status": status, "offset": offset})
            for pid, space, title, kind in db.execute(
                    """SELECT content_id,space,title,content_type
                       FROM confluence_inventory_items WHERE scope_id=?""", (sid,)):
                pages[pid] = {"id": pid, "space": space, "title": title,
                              "type": kind}
        return {"pages": list(pages.values()), "scopes": statuses,
                "coverage": "complete" if statuses and all(
                    x["status"] == "complete" for x in statuses) else "partial"}
    finally:
        db.close()
