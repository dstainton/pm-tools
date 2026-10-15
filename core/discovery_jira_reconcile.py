"""Read-only Jira project reconciliation against locally stored source IDs.

Only a fully completed fresh project search can establish an issue is absent
from that search. Absence is not proof of deletion: permissions, moves, and
project access can change. No source records are removed automatically.
"""
import sqlite3
from core import sources


def reconcile(cfg, projects, db_path):
    projects = list(dict.fromkeys(str(p).strip() for p in projects if p))
    if not projects:
        return {"coverage": "unconfigured", "projects": []}
    db = sqlite3.connect(str(db_path))
    outcome = {"coverage": "complete", "projects": []}
    try:
        db.execute("""CREATE TABLE IF NOT EXISTS jira_missing_observations (
            project TEXT NOT NULL, issue_key TEXT NOT NULL,
            checked_at TEXT NOT NULL, classification TEXT NOT NULL,
            PRIMARY KEY(project, issue_key))""")
        for project in projects:
            state = {"project": project, "status": "unavailable",
                     "missing_candidates": 0, "detail": ""}
            outcome["projects"].append(state)
            checkpoint = db.execute(
                "SELECT complete, source_url FROM jira_progress WHERE project=?",
                (project,)).fetchone()
            source = cfg["jira"]["base_url"].rstrip("/")
            if not checkpoint or not checkpoint[0]:
                state["detail"] = "Complete baseline inventory required"
            elif checkpoint[1] and checkpoint[1] != source:
                state["detail"] = "Checkpoint belongs to another Jira endpoint"
            else:
                escaped = project.replace("\\", "\\\\").replace('"', '\\"')
                query = 'project = "' + escaped + '" ORDER BY key ASC'
                try:
                    fresh = sources.search_issues(cfg["jira"], query,
                        fields=["key"], max_items=0, with_metadata=True)
                    if not fresh.get("complete"):
                        state["status"] = "incomplete"
                        state["detail"] = fresh.get("reason") or "Incomplete Jira search"
                    else:
                        remote = {str(x["key"]) for x in fresh["issues"] if x.get("key")}
                        if len(remote) != len(fresh["issues"]):
                            raise ValueError("Missing or duplicate issue keys in Jira search")
                        stored = {x[0] for x in db.execute(
                            "SELECT issue_key FROM jira_raw_issues WHERE project=?", (project,))}
                        missing = sorted(stored - remote)
                        import datetime as dt
                        now = dt.datetime.now(dt.timezone.utc).isoformat()
                        with db:
                            db.execute("DELETE FROM jira_missing_observations WHERE project=?", (project,))
                            db.executemany("""INSERT INTO jira_missing_observations
                                (project, issue_key, checked_at, classification)
                                VALUES (?, ?, ?, ?)""",
                                [(project, key, now, "absent from complete project search")
                                 for key in missing])
                        state["status"] = "complete"
                        state["missing_candidates"] = len(missing)
                        state["detail"] = "Absence is not proof of deletion or revoked access"
                except Exception as exc:
                    state["detail"] = "{}: {}".format(type(exc).__name__, str(exc)[:160])
            if state["status"] != "complete":
                outcome["coverage"] = "partial"
        return outcome
    finally:
        db.close()
