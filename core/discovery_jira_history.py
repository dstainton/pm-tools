"""Resumable Jira issue changelog extraction for historical taxonomy evidence.

Changelog entries are observations. They do not automatically establish
renames, ownership changes, or current product definitions.
"""
import json
import sqlite3
from urllib.parse import quote

from core import sources

INTEREST = {"labels", "component", "components", "parent", "status",
            "issuetype", "fix version", "fixversion", "epic link"}


def _setup(db):
    db.execute("""CREATE TABLE IF NOT EXISTS jira_history_progress (
        issue_key TEXT PRIMARY KEY,
        next_start INTEGER NOT NULL DEFAULT 0,
        complete INTEGER NOT NULL DEFAULT 0
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS jira_history_events (
        issue_key TEXT NOT NULL,
        history_id TEXT NOT NULL,
        event_time TEXT,
        author TEXT,
        field_name TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT,
        PRIMARY KEY(issue_key, history_id, field_name)
    )""")
    db.commit()


def collect(cfg, db_path, max_issues=20, page_size=100):
    """Hydrate accessible issues a bounded amount per invocation.

    Pagination and storage are transactional per page. Unavailable history is
    explicitly reported; other issues continue. Re-running is idempotent.
    """
    if max_issues < 1 or page_size < 1:
        raise ValueError("max_issues and page_size must be positive")
    db = sqlite3.connect(str(db_path))
    try:
        _setup(db)
        issues = db.execute("""SELECT DISTINCT i.issue_key FROM jira_raw_issues AS i
            LEFT JOIN jira_history_progress AS p ON i.issue_key=p.issue_key
            WHERE COALESCE(p.complete, 0)=0 ORDER BY i.issue_key LIMIT ?""",
                            (max_issues,)).fetchall()
        result = {"attempted": 0, "completed": 0, "incomplete": 0,
                  "errors": [], "coverage": "complete"}
        jira = cfg["jira"]
        for (key,) in issues:
            result["attempted"] += 1
            row = db.execute(
                "SELECT next_start FROM jira_history_progress WHERE issue_key=?",
                (key,)).fetchone()
            start = row[0] if row else 0
            try:
                response = sources.send(
                    "GET", jira["base_url"].rstrip("/") + "/rest/api/3/issue/" +
                    quote(key, safe="") + "/changelog",
                    params={"startAt": start, "maxResults": page_size},
                    auth=(jira["email"], jira["api_token"]),
                    headers={"Accept": "application/json"}, timeout=60)
                response.raise_for_status()
                data = response.json()
                values = data.get("values")
                if not isinstance(values, list):
                    raise ValueError("Missing Jira changelog values")
                total = data.get("total")
                end = start + len(values)
                done = bool(data.get("isLast")) or (
                    total is not None and end >= int(total))
                if not values and not done:
                    raise ValueError("Empty changelog page without completion")
                with db:
                    for event in values:
                        event_id = str(event.get("id") or "")
                        if not event_id:
                            raise ValueError("Changelog entry missing id")
                        author = (event.get("author") or {}).get("accountId")
                        for item in event.get("items") or []:
                            field = str(item.get("field") or "")
                            if field.casefold() not in INTEREST:
                                continue
                            # A history entry may contain multiple values for
                            # one field; key by item position to avoid loss.
                            ordinal = (event.get("items") or []).index(item)
                            db.execute("""INSERT OR REPLACE INTO jira_history_events
                                (issue_key, history_id, event_time, author,
                                 field_name, old_value, new_value)
                                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                (key, event_id + ":" + str(ordinal),
                                 event.get("created"), author, field,
                                 item.get("fromString") or item.get("from"),
                                 item.get("toString") or item.get("to")))
                    db.execute("""INSERT INTO jira_history_progress
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
                result["errors"].append({"issue": key,
                                         "detail": "{}: {}".format(
                                             type(exc).__name__, str(exc)[:140])})
        pending = db.execute("""SELECT COUNT(*) FROM jira_raw_issues i
            LEFT JOIN jira_history_progress p ON p.issue_key=i.issue_key
            WHERE COALESCE(p.complete, 0)=0""").fetchone()[0]
        if pending:
            result["coverage"] = "partial"
        result["remaining"] = pending
        return result
    finally:
        db.close()
