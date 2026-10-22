"""Persistent, read-only Jira inventory collection with transactional checkpoints.

Source scopes are Jira projects, never inferred workstream filters. Raw issue
payloads are stored before derived interpretation so evidence can be reindexed.
"""
import json
import sqlite3

from core import discovery_jira_inventory, sources


def _database(path):
    db = sqlite3.connect(str(path))
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("""CREATE TABLE IF NOT EXISTS jira_progress (
        project TEXT PRIMARY KEY,
        continuation TEXT,
        complete INTEGER NOT NULL DEFAULT 0,
        page_count INTEGER NOT NULL DEFAULT 0,
        source_url TEXT,
        refreshed_at TEXT
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS jira_raw_issues (
        project TEXT NOT NULL,
        issue_key TEXT NOT NULL,
        payload TEXT NOT NULL,
        PRIMARY KEY(project, issue_key)
    )""")
    cols = {row[1] for row in db.execute("PRAGMA table_info(jira_progress)")}
    if "source_url" not in cols:
        db.execute("ALTER TABLE jira_progress ADD COLUMN source_url TEXT")
    if "refreshed_at" not in cols:
        db.execute("ALTER TABLE jira_progress ADD COLUMN refreshed_at TEXT")
    db.commit()
    return db


def crawl(cfg, projects, db_path, page_limit=20, page_size=100, on_progress=None):
    """Persist at most page_limit Jira pages per project and report coverage.

    A failed request leaves the last committed continuation untouched. A
    complete project is a snapshot at retrieval time, not a live change feed.
    A separate refresh workflow will recheck updated/deleted issues.
    """
    if page_limit < 1 or page_size < 1:
        raise ValueError("page_limit and page_size must be positive")
    result = {"projects": [], "coverage": "complete"}
    projects = list(dict.fromkeys(str(p).strip() for p in projects if p))
    if not projects:
        return {"projects": [], "coverage": "unconfigured"}
    db = _database(db_path)
    try:
        for project in projects:
            row = db.execute("SELECT continuation, complete, page_count, source_url FROM jira_progress WHERE project=?",
                             (project,)).fetchone()
            token, complete, total_pages, source_url = row if row else (None, 0, 0, None)
            state = {"project": project, "status": "complete" if complete else "incomplete",
                     "fetched_pages": 0, "stored": 0}
            result["projects"].append(state)
            canonical_source = cfg["jira"]["base_url"].rstrip("/")
            if source_url and source_url != canonical_source:
                state["status"] = "unavailable"
                state["detail"] = "Checkpoint belongs to a different Jira endpoint"
                result["coverage"] = "partial"
                continue
            if complete:
                state["stored"] = db.execute(
                    "SELECT COUNT(*) FROM jira_raw_issues WHERE project=?", (project,)).fetchone()[0]
                continue
            jira = cfg["jira"]
            escaped = project.replace("\\", "\\\\").replace('"', '\\"')
            jql = 'project = "' + escaped + '" ORDER BY key ASC'
            # Prevent a backend returning the same cursor indefinitely.
            tokens_seen = {token} if token else set()
            for _ in range(page_limit):
                request = {"jql": jql, "fields": discovery_jira_inventory.FIELDS,
                           "maxResults": page_size}
                if token:
                    request["nextPageToken"] = token
                try:
                    response = sources.send(
                        "POST", jira["base_url"].rstrip("/") + "/rest/api/3/search/jql",
                        json=request,
                        auth=(jira["email"], jira["api_token"]),
                        headers={"Accept": "application/json"}, timeout=60)
                    response.raise_for_status()
                    payload = response.json()
                    issues = payload.get("issues")
                    if not isinstance(issues, list):
                        raise ValueError("Jira search did not return an issues list")
                    next_token = payload.get("nextPageToken") or None
                    if next_token and (not issues or next_token == token or next_token in tokens_seen):
                        raise ValueError("Jira pagination did not advance")
                    # No cursor means completion. For Jira APIs exposing
                    # isLast, accept that signal as well.
                    done = not next_token or payload.get("isLast") is True
                    with db:
                        for issue in issues:
                            key = issue.get("key")
                            if not key:
                                raise ValueError("Jira returned an issue without a key")
                            db.execute("""INSERT INTO jira_raw_issues(project, issue_key, payload)
                                VALUES(?, ?, ?) ON CONFLICT(project, issue_key)
                                DO UPDATE SET payload=excluded.payload""",
                                (project, str(key), json.dumps(issue, ensure_ascii=False)))
                        db.execute("""INSERT INTO jira_progress(project, continuation, complete, page_count, source_url)
                            VALUES(?, ?, ?, ?, ?) ON CONFLICT(project)
                            DO UPDATE SET continuation=excluded.continuation,
                            complete=excluded.complete, page_count=excluded.page_count,
                            source_url=excluded.source_url""",
                            (project, None if done else next_token, int(done), total_pages + 1,
                             canonical_source))
                    total_pages += 1
                    state["fetched_pages"] += 1
                    if on_progress is not None:
                        stored = db.execute(
                            "SELECT COUNT(*) FROM jira_raw_issues WHERE project=?",
                            (project,)).fetchone()[0]
                        on_progress(project, stored, total_pages, done)
                    token = next_token
                    if token:
                        tokens_seen.add(token)
                    if done:
                        state["status"] = "complete"
                        break
                except Exception as exc:
                    state["detail"] = "{}: {}".format(type(exc).__name__, str(exc)[:160])
                    break
            state["stored"] = db.execute(
                "SELECT COUNT(*) FROM jira_raw_issues WHERE project=?", (project,)).fetchone()[0]
            if state["status"] != "complete":
                result["coverage"] = "partial"
        return result
    finally:
        db.close()


def refresh(cfg, projects, db_path, overlap_days=2, page_size=100):
    """Incrementally refresh completed project snapshots without discarding history.

    A safety overlap re-reads recent issues. The stored watermark advances only
    after an entire paginated refresh succeeds. Deletions and permission losses
    cannot be inferred from an updated-since query and are not claimed.
    """
    import datetime as dt
    if overlap_days < 0 or page_size < 1:
        raise ValueError("overlap_days must be nonnegative and page_size positive")
    projects = list(dict.fromkeys(str(p).strip() for p in projects if p))
    if not projects:
        return {"coverage": "unconfigured", "projects": []}
    db = _database(db_path)
    output = {"coverage": "complete", "projects": []}
    try:
        for project in projects:
            status = {"project": project, "status": "unavailable", "updated": 0}
            output["projects"].append(status)
            row = db.execute(
                "SELECT complete, source_url, refreshed_at FROM jira_progress WHERE project=?",
                (project,)).fetchone()
            jira = cfg["jira"]
            source = jira["base_url"].rstrip("/")
            if not row or not row[0]:
                status["detail"] = "Complete baseline inventory required before refresh"
            elif row[1] and row[1] != source:
                status["detail"] = "Checkpoint belongs to a different Jira endpoint"
            else:
                # The first refresh reads changes since the stored baseline's
                # last observed updated date, never merely since today's date.
                last = row[2]
                if last is None:
                    dates = [json.loads(r[0]).get("fields", {}).get("updated")
                             for r in db.execute(
                                 "SELECT payload FROM jira_raw_issues WHERE project=?", (project,))]
                    last = max((str(x) for x in dates if x), default=None)
                # A missing watermark warrants full project recheck.
                if last:
                    try:
                        stamp = dt.datetime.fromisoformat(last.replace("Z", "+00:00"))
                        if stamp.tzinfo is None:
                            stamp = stamp.replace(tzinfo=dt.timezone.utc)
                        since = (stamp - dt.timedelta(days=overlap_days)).astimezone(
                            dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
                    except ValueError:
                        since = None
                else:
                    since = None
                escaped = project.replace("\\", "\\\\").replace('"', '\\"')
                jql = 'project = "' + escaped + '"'
                if since:
                    jql += ' AND updated >= "' + since + '"'
                jql += " ORDER BY updated ASC, key ASC"
                try:
                    refresh_started = dt.datetime.now(dt.timezone.utc).isoformat()
                    records = sources.search_issues(jira, jql,
                        fields=discovery_jira_inventory.FIELDS,
                        max_items=0, page_size=page_size, with_metadata=True)
                    if not records.get("complete"):
                        status["status"] = "incomplete"
                        status["detail"] = records.get("reason") or "Partial refresh"
                    else:
                        # Commit changes and watermark together. The overlap
                        # prevents skipped records near the boundary.
                        with db:
                            history_tables = {r[0] for r in db.execute(
                                "SELECT name FROM sqlite_master WHERE type='table'")}
                            for issue in records["issues"]:
                                key = issue.get("key")
                                if not key:
                                    raise ValueError("Jira refresh returned missing issue key")
                                serialized = json.dumps(issue, ensure_ascii=False, sort_keys=True)
                                previous = db.execute(
                                    "SELECT payload FROM jira_raw_issues WHERE project=? AND issue_key=?",
                                    (project, str(key))).fetchone()
                                db.execute("""INSERT INTO jira_raw_issues(project, issue_key, payload)
                                    VALUES(?, ?, ?) ON CONFLICT(project, issue_key)
                                    DO UPDATE SET payload=excluded.payload""",
                                    (project, str(key), serialized))
                                # Changed source records need a new full pass over
                                # comments/changelog. Keep old events as evidence.
                                if previous is None or json.loads(previous[0]) != issue:
                                    if "jira_history_progress" in history_tables:
                                        db.execute("""UPDATE jira_history_progress
                                            SET next_start=0, complete=0 WHERE issue_key=?""",
                                            (str(key),))
                                    if "jira_comment_progress" in history_tables:
                                        db.execute("""UPDATE jira_comment_progress
                                            SET next_start=0, complete=0 WHERE issue_key=?""",
                                            (str(key),))
                            db.execute("UPDATE jira_progress SET refreshed_at=? WHERE project=?",
                                       (refresh_started, project))
                        status["status"] = "complete"
                        status["updated"] = len(records["issues"])
                except Exception as exc:
                    status["detail"] = "{}: {}".format(type(exc).__name__, str(exc)[:160])
            if status["status"] != "complete":
                output["coverage"] = "partial"
        return output
    finally:
        db.close()
