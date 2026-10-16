"""Checkpointed, bounded Confluence page inventory respecting configured scope.

Page trees use Confluence Cloud v2 cursor-paginated descendants. Whole-space
scopes retain bounded CQL offsets. Checkpoints remain bound to the authorized
root and space. No content is downloaded or modified.
"""
import hashlib
import json
import sqlite3

from core import discovery_inventory, sources

# v1/v2 used offset-based CQL page-tree searches; three APS scopes repeated
# at offset 1000. Restart incomplete old cursors via the v2 descendants API.
SCAN_VERSION = 4


def _init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS confluence_inventory_cursor (
        scope_id TEXT PRIMARY KEY, scope_json TEXT NOT NULL,
        offset INTEGER NOT NULL, status TEXT NOT NULL, error TEXT,
        scan_version INTEGER NOT NULL DEFAULT 1,
        cursor TEXT)""")
    if "scan_version" not in {row[1] for row in db.execute(
            "PRAGMA table_info(confluence_inventory_cursor)")}:
        db.execute("ALTER TABLE confluence_inventory_cursor "
                   "ADD COLUMN scan_version INTEGER NOT NULL DEFAULT 1")
    if "cursor" not in {row[1] for row in db.execute(
            "PRAGMA table_info(confluence_inventory_cursor)")}:
        db.execute("ALTER TABLE confluence_inventory_cursor ADD COLUMN cursor TEXT")
    db.execute("""CREATE TABLE IF NOT EXISTS confluence_inventory_items (
        scope_id TEXT NOT NULL, content_id TEXT NOT NULL, space TEXT,
        title TEXT, content_type TEXT, updated TEXT, ancestors TEXT,
        PRIMARY KEY(scope_id, content_id))""")
    # Track all hierarchy nodes to recognize covered nested folder roots, but
    # index only actual page bodies. Never fetch folders as pages or comments.
    db.execute("""CREATE TABLE IF NOT EXISTS confluence_inventory_nodes (
        scope_id TEXT NOT NULL, content_id TEXT NOT NULL,
        title TEXT, content_type TEXT,
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
        if db.execute("""SELECT 1 FROM confluence_inventory_nodes
                         WHERE scope_id=? AND content_id=?
                         UNION
                         SELECT 1 FROM confluence_inventory_items
                         WHERE scope_id=? AND content_id=?""",
                      (parent_id, child_id, parent_id, child_id)).fetchone():
            return parent
    return None


def crawl(cfg, db_path, max_rows=100, on_progress=None):
    """Resume bounded page-tree cursor or space-offset collection.

    Broken legacy CQL page-tree offsets are replaced with v2 descendant cursors
    once, while preserving previously indexed source documents.
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
                    """SELECT offset, status, scan_version, cursor
                       FROM confluence_inventory_cursor WHERE scope_id=?""",
                    (sid,)).fetchone()
                offset, status, version, cursor = record if record else (0, "pending", SCAN_VERSION, None)
                # Page-tree v3 inventories lacked folder-root handling and
                # did not retain non-page nodes. Revalidate even those marked
                # complete, without discarding previously indexed documents.
                if (record and version < SCAN_VERSION
                        and scope["type"] == "page_tree"):
                    with db:
                        db.execute("""UPDATE confluence_inventory_cursor
                                      SET offset=0, cursor=NULL, status='pending', error=NULL,
                                          scan_version=? WHERE scope_id=?""",
                                   (SCAN_VERSION, sid))
                    offset, status, cursor = 0, "pending", None
                    entry["legacy_checkpoint_restarted"] = True

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
                                      SET scan_version=? WHERE scope_id=?""",
                                   (SCAN_VERSION, sid))

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
                    if scope["type"] == "page_tree":
                        rows, next_cursor = sources.list_confluence_page_descendants(
                            cfg, scope["root_id"], cursor=cursor,
                            limit=min(100, remaining))
                        more = next_cursor is not None
                        if more and next_cursor == cursor:
                            raise ValueError(
                                "Confluence v2 descendants returned the same cursor twice")
                    else:
                        rows, more = sources.list_confluence_inventory(
                            cfg, scope["space"], start=offset,
                            limit=min(25, remaining))
                        next_cursor = None
                    if not rows and more:
                        raise ValueError("Confluence returned an empty page with a continuation link")
                    ids = tuple(str(row.get("id") or "") for row in rows)
                    if rows and ids in signatures:
                        raise ValueError(
                            "Repeated Confluence results at offset {}: "
                            "the server/cache did not advance; stopped safely".format(offset))
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
                        # v2 descendants includes all depths; ignore non-pages
                        # while still advancing its opaque cursor correctly.
                        if scope["type"] == "page_tree" and row.get("type") != "page":
                            continue
                        # In legacy CQL space searches ancestry is only metadata.
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

                    if rows and not to_write and scope["type"] != "page_tree":
                        raise ValueError("Confluence returned only results without page IDs")
                    offset += len(rows)
                    remaining -= len(rows)
                    status = "complete" if not more else "incomplete"
                    with db:
                        db.executemany("""INSERT OR REPLACE INTO confluence_inventory_items
                            (scope_id,content_id,space,title,content_type,updated,ancestors)
                            VALUES(?,?,?,?,?,?,?)""", to_write)
                        db.execute("""INSERT INTO confluence_inventory_cursor
                            (scope_id,scope_json,offset,status,error,scan_version,cursor)
                            VALUES(?,?,?,?,NULL,?,?)
                            ON CONFLICT(scope_id) DO UPDATE SET
                                scope_json=excluded.scope_json,
                                offset=excluded.offset, status=excluded.status,
                                error=NULL, scan_version=excluded.scan_version,
                                cursor=excluded.cursor""",
                            (sid, json.dumps(scope, sort_keys=True), offset,
                             status, SCAN_VERSION, next_cursor))
                    cursor = next_cursor
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
                # A child tree intentionally skipped during crawling may have
                # no cursor of its own. Resolve its unique root only from
                # completed, already authorized ancestor inventory rows.
                covered = []
                if configured["type"] == "page_tree":
                    for parent_id, parent in completed:
                        if parent.get("type") != "page_tree":
                            continue
                        if (configured.get("space") and
                                configured["space"] != parent.get("space")):
                            continue
                        if configured.get("root_id"):
                            ids = [configured["root_id"]]
                        elif configured.get("root_title"):
                            ids = [r[0] for r in db.execute(
                                """SELECT content_id FROM confluence_inventory_items
                                   WHERE scope_id=? AND title=?""",
                                (parent_id, configured["root_title"]))]
                        else:
                            ids = []
                        for child_id in ids:
                            if str(child_id) != parent.get("root_id") and db.execute(
                                    """SELECT 1 FROM confluence_inventory_items
                                       WHERE scope_id=? AND content_id=?""",
                                    (parent_id, str(child_id))).fetchone():
                                covered.append((str(child_id), parent))
                if len({item[0] for item in covered}) == 1:
                    statuses.append({"scope": configured, "status": "complete",
                                     "covered_by": covered[0][1]["root_id"],
                                     "detail": "Covered by complete ancestor page tree"})
                else:
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
