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
        page_count INTEGER NOT NULL DEFAULT 0
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS jira_raw_issues (
        project TEXT NOT NULL,
        issue_key TEXT NOT NULL,
        payload TEXT NOT NULL,
        PRIMARY KEY(project, issue_key)
    )""")
    db.commit()
    return db


def crawl(cfg, projects, db_path, page_limit=20, page_size=100):
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
            row = db.execute("SELECT continuation, complete, page_count FROM jira_progress WHERE project=?",
                             (project,)).fetchone()
            token, complete, total_pages = row if row else (None, 0, 0)
            state = {"project": project, "status": "complete" if complete else "incomplete",
                     "fetched_pages": 0, "stored": 0}
            result["projects"].append(state)
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
                        db.execute("""INSERT INTO jira_progress(project, continuation, complete, page_count)
                            VALUES(?, ?, ?, ?) ON CONFLICT(project)
                            DO UPDATE SET continuation=excluded.continuation,
                            complete=excluded.complete, page_count=excluded.page_count""",
                            (project, None if done else next_token, int(done), total_pages + 1))
                    total_pages += 1
                    state["fetched_pages"] += 1
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
