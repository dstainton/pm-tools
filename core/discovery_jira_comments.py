"""Resumable Jira comment collection without inference or Jira writes."""
import json
import sqlite3
from urllib.parse import quote

from core import discovery_jira_guard, sources


def collect(cfg, db_path, max_issues=20, page_size=100):
    if max_issues < 1 or page_size < 1:
        raise ValueError("max_issues and page_size must be positive")
    db = sqlite3.connect(str(db_path))
    try:
        db.execute("""CREATE TABLE IF NOT EXISTS jira_comment_progress (
            issue_key TEXT PRIMARY KEY, next_start INTEGER NOT NULL DEFAULT 0,
            complete INTEGER NOT NULL DEFAULT 0)""")
        db.execute("""CREATE TABLE IF NOT EXISTS jira_comments (
            issue_key TEXT NOT NULL, comment_id TEXT NOT NULL,
            created_at TEXT, updated_at TEXT, author_id TEXT,
            payload TEXT NOT NULL, PRIMARY KEY(issue_key, comment_id))""")
        db.commit()
        discovery_jira_guard.check(db, cfg)
        issues = db.execute("""SELECT DISTINCT i.issue_key FROM jira_raw_issues i
            LEFT JOIN jira_comment_progress p ON p.issue_key=i.issue_key
            WHERE COALESCE(p.complete, 0)=0 ORDER BY i.issue_key LIMIT ?""",
            (max_issues,)).fetchall()
        result = {"coverage": "complete", "attempted": 0, "completed": 0,
                  "incomplete": 0, "errors": []}
        jira = cfg["jira"]
        for (key,) in issues:
            result["attempted"] += 1
            row = db.execute("SELECT next_start FROM jira_comment_progress WHERE issue_key=?",
                             (key,)).fetchone()
            start = row[0] if row else 0
            try:
                response = sources.send(
                    "GET", jira["base_url"].rstrip("/") + "/rest/api/3/issue/" +
                    quote(key, safe="") + "/comment",
                    params={"startAt": start, "maxResults": page_size},
                    auth=(jira["email"], jira["api_token"]),
                    headers={"Accept": "application/json"}, timeout=60)
                response.raise_for_status()
                data = response.json()
                comments = data.get("comments")
                if not isinstance(comments, list) or data.get("total") is None:
                    raise ValueError("Missing Jira comments or pagination metadata")
                end = start + len(comments)
                total = int(data["total"])
                if end < total and not comments:
                    raise ValueError("Empty comment page before completion")
                done = end >= total
                with db:
                    for comment in comments:
                        identity = comment.get("id")
                        if identity is None:
                            raise ValueError("Comment missing ID")
                        db.execute("""INSERT INTO jira_comments
                            (issue_key, comment_id, created_at, updated_at,
                             author_id, payload) VALUES (?, ?, ?, ?, ?, ?)
                            ON CONFLICT(issue_key, comment_id)
                            DO UPDATE SET created_at=excluded.created_at,
                            updated_at=excluded.updated_at,
                            author_id=excluded.author_id, payload=excluded.payload""",
                            (key, str(identity), comment.get("created"),
                             comment.get("updated"),
                             (comment.get("author") or {}).get("accountId"),
                             json.dumps(comment, ensure_ascii=False)))
                    db.execute("""INSERT INTO jira_comment_progress
                        (issue_key, next_start, complete) VALUES (?, ?, ?)
                        ON CONFLICT(issue_key) DO UPDATE SET
                        next_start=excluded.next_start, complete=excluded.complete""",
                        (key, end, int(done)))
                if done:
                    result["completed"] += 1
                else:
                    result["incomplete"] += 1
            except Exception as exc:
                result["incomplete"] += 1
                result["errors"].append({"issue": key, "detail":
                                         "{}: {}".format(type(exc).__name__, str(exc)[:140])})
        result["remaining"] = db.execute("""SELECT COUNT(*) FROM jira_raw_issues i
            LEFT JOIN jira_comment_progress p ON p.issue_key=i.issue_key
            WHERE COALESCE(p.complete, 0)=0""").fetchone()[0]
        if result["remaining"]:
            result["coverage"] = "partial"
        return result
    finally:
        db.close()
