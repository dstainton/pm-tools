"""Checkpointed, bounded Confluence page inventory respecting configured scope.

This collector is independent of the older capped metadata report. Every run
continues at a persisted CQL offset; the current scope is bound to a fingerprint
of the authorized root and space. No content is downloaded or modified.
"""
import hashlib
import json
import sqlite3

from core import discovery_inventory, sources

# v1 silently dropped valid CQL matches and could advance indefinitely over
# repeated pages. Restart incomplete v1 offsets once, without deleting pages.
SCAN_VERSION = 2


def _init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS confluence_inventory_cursor (
        scope_id TEXT PRIMARY KEY, scope_json TEXT NOT NULL,
        offset INTEGER NOT NULL, status TEXT NOT NULL, error TEXT,
        scan_version INTEGER NOT NULL DEFAULT 1)""")
    if "scan_version" not in {row[1] for row in db.execute(
            "PRAGMA table_info(confluence_inventory_cursor)")}:
        db.execute("ALTER TABLE confluence_inventory_cursor "
                   "ADD COLUMN scan_version INTEGER NOT NULL DEFAULT 1")
    db.execute("""CREATE TABLE IF NOT EXISTS confluence_inventory_items (
        scope_id TEXT NOT NULL, content_id TEXT NOT NULL, space TEXT,
        title TEXT, content_type TEXT, updated TEXT, ancestors TEXT,
        PRIMARY KEY(scope_id, content_id))""")
    db.commit()


def _identity(scope):
    key = json.dumps(scope, sort_keys=True)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _is_covered(db, complete_scopes, child_scope):
    """A completed authorized tree covers a configured descendant page tree."""
    if child_scope["type"] != "page_tree":
        return None
    child_id = str(child_scope["root_id"])
    for parent_id, parent in complete_scopes:
        if parent["type"] != "page_tree" or parent["root_id"] == child_id:
            continue
        if parent.get("space") != child_scope.get("space"):
            continue
        if db.execute("""SELECT 1 FROM confluence_inventory_items
                         WHERE scope_id=? AND content_id=?""",
                      (parent_id, child_id)).fetchone():
            return parent
    return None


def crawl(cfg, db_path, max_rows=100, on_progress=None):
    """Resume bounded, source-cited CQL traversal without trusting ancestry JSON.

    Stop on repeated page batches instead of advancing meaningless offsets.
    Legacy incomplete cursors are rescanned from zero exactly once, preserving
    existing inventory and already indexed evidence.
    """
    if max_rows < 1:
        raise ValueError("max_rows must be positive")
    scopes = discovery_inventory._scopes(cfg)
    db = sqlite3.connect(str(db_path))
    results = []
    completed = []

    def emit(scope, status, offset, processed, index, total):
        if on_progress is not None:
            name = ("Space " + str(scope.get("space") or "unknown")
                    if scope.get("type") == "space"
                    else "Page tree " + str(scope.get("root_title") or
                                            scope.get("root_id") or "unknown"))
            on_progress({"name": name, "status": status, "offset": offset,
                         "processed": processed, "index": index, "total": total})

    try:
        _init(db)
        for scope_index, configured in enumerate(scopes, 1):
            entry = {"scope": configured, "status": "unavailable",
                     "processed": 0, "new_pages": 0, "duplicates": 0,
                     "ancestry_metadata_warnings": 0}
            results.append(entry)
            sid = None
            try:
                resolved = discovery_inventory._resolve(cfg, configured)
                scope, root = resolved if isinstance(resolved, tuple) else (resolved, None)
                sid = _identity(scope)
                record = db.execute(
                    """SELECT offset, status, scan_version
                       FROM confluence_inventory_cursor WHERE scope_id=?""",
                    (sid,)).fetchone()
                offset, status, version = record if record else (0, "pending", SCAN_VERSION)
                if status == "complete":
                    entry.update(status="complete", offset=offset, scope=scope)
                    completed.append((sid, scope))
                    emit(scope, "complete", offset, 0, scope_index, len(scopes))
                    continue

                # Only a *complete* previously authorized ancestor can replace
                # a descendant crawl. Merely sharing a Confluence space cannot.
                parent = _is_covered(db, completed, scope)
                if parent:
                    entry.update(status="complete", scope=scope, offset=offset,
                                 covered_by=parent["root_id"])
                    emit(scope, "complete", offset, 0, scope_index, len(scopes))
                    continue

                if record and version < SCAN_VERSION:
                    with db:
                        db.execute("""UPDATE confluence_inventory_cursor
                                      SET offset=0, status='pending', error=NULL,
                                          scan_version=? WHERE scope_id=?""",
                                   (SCAN_VERSION, sid))
                    offset, status = 0, "pending"
                    entry["legacy_checkpoint_restarted"] = True

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

                known_ids = {r[0] for r in db.execute(
                    "SELECT content_id FROM confluence_inventory_items WHERE scope_id=?",
                    (sid,))}
                signatures = set()
                remaining = max_rows
                while remaining:
                    rows, more = sources.list_confluence_inventory(
                        cfg, scope.get("space"), start=offset,
                        limit=min(25, remaining),
                        ancestor_id=scope["root_id"] if scope["type"] == "page_tree" else None)
                    if not rows and more:
                        raise ValueError("Confluence returned an empty page with a continuation link")
                    ids = tuple(str(row.get("id") or "") for row in rows)
                    if rows and ids in signatures:
                        raise ValueError("Repeated Confluence results at offset {}: "
                                         "the server/cache did not advance; stopped safely"
                                         .format(offset))
                    if rows:
                        signatures.add(ids)

                    new = 0
                    duplicates = 0
                    warnings = 0
                    to_write = []
                    for row in rows:
                        pid = str(row.get("id") or "")
                        if not pid:
                            continue
                        # The server-side CQL 'ancestor' predicate is the scope
                        # authority; expanded ancestry may omit deep parents.
                        ancestors = [str(a.get("id")) for a in
                                     (row.get("ancestors") or [])
                                     if isinstance(a, dict) and a.get("id")]
                        if (scope["type"] == "page_tree" and ancestors and
                                scope["root_id"] not in ancestors and
                                pid != scope["root_id"]):
                            warnings += 1
                        if pid in known_ids:
                            duplicates += 1
                        else:
                            known_ids.add(pid)
                            new += 1
                        to_write.append((
                            sid, pid, scope.get("space"), row.get("title") or "",
                            row.get("type") or "page",
                            (row.get("version") or {}).get("when"),
                            json.dumps(ancestors)))

                    if rows and not to_write:
                        raise ValueError("Confluence returned only results without page IDs")
                    offset += len(rows)
                    remaining -= len(rows)
                    status = "complete" if not more else "incomplete"
                    with db:
                        db.executemany("""INSERT OR REPLACE INTO confluence_inventory_items
                            (scope_id,content_id,space,title,content_type,updated,ancestors)
                            VALUES(?,?,?,?,?,?,?)""", to_write)
                        db.execute("""INSERT INTO confluence_inventory_cursor
                            (scope_id,scope_json,offset,status,error,scan_version)
                            VALUES(?,?,?,?,NULL,?)
                            ON CONFLICT(scope_id) DO UPDATE SET
                                scope_json=excluded.scope_json,
                                offset=excluded.offset, status=excluded.status,
                                error=NULL, scan_version=excluded.scan_version""",
                            (sid, json.dumps(scope, sort_keys=True), offset,
                             status, SCAN_VERSION))
                    entry["processed"] += len(rows)
                    entry["offset"] = offset
                    entry["new_pages"] += new
                    entry["duplicates"] += duplicates
                    entry["ancestry_metadata_warnings"] += warnings
                    emit(scope, status, offset, entry["processed"],
                         scope_index, len(scopes))
                    if not more:
                        break
                entry.update(scope=scope, offset=offset, status=status)
                if status == "complete":
                    completed.append((sid, scope))
            except Exception as exc:
                message = "{}: {}".format(type(exc).__name__, str(exc)[:200])
                entry.update(status="incomplete", error=message)
                if sid is not None:
                    with db:
                        db.execute("""UPDATE confluence_inventory_cursor
                                      SET error=?, status='incomplete'
                                      WHERE scope_id=?""", (message, sid))
                emit(entry.get("scope", configured), "incomplete",
                     entry.get("offset", 0), entry["processed"],
                     scope_index, len(scopes))
        return results
    finally:
        db.close()


def indexed_inventory(cfg, db_path):
    """Load distinct pages from authorized scopes, including covered children.

    A configured child tree can be satisfied by an independently completed
    ancestor tree only when the child root ID is explicitly in that inventory.
    An incomplete legacy checkpoint never establishes completeness by itself.
    """
    db = sqlite3.connect(str(db_path))
    try:
        _init(db)
        records = []
        for sid, raw, status, offset in db.execute(
                "SELECT scope_id, scope_json, status, offset "
                "FROM confluence_inventory_cursor"):
            records.append((sid, json.loads(raw), status, offset))
        completed = [(sid, scope) for sid, scope, status, _ in records
                     if status == "complete"]
        pages = {}
        statuses = []
        for configured in discovery_inventory._scopes(cfg):
            matches = []
            for sid, scope, status, offset in records:
                if scope.get("type") != configured["type"]:
                    continue
                if configured.get("space") and configured["space"] != scope.get("space"):
                    continue
                if configured["type"] == "page_tree":
                    if (configured.get("root_id") and
                            configured["root_id"] != scope.get("root_id")):
                        continue
                    if (configured.get("root_title") and
                            configured["root_title"] != scope.get("root_title")):
                        continue
                matches.append((sid, scope, status, offset))
            if len(matches) != 1:
                statuses.append({"scope": configured, "status": "unavailable",
                                 "detail": "No unique checkpoint for this authorized scope"})
                continue
            sid, scope, status, offset = matches[0]
            parent = _is_covered(db, completed, scope) if status != "complete" else None
            if parent:
                statuses.append({"scope": configured, "status": "complete",
                                 "covered_by": parent["root_id"],
                                 "detail": "Covered by complete ancestor page tree"})
                continue
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
