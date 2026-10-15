"""Ensure auxiliary Jira history collectors cannot cross server boundaries.

The baseline project's endpoint identity is persisted by the inventory crawler.
Fail closed before retrieving or writing any historical source evidence.
"""
def check(db, cfg):
    expected = cfg["jira"]["base_url"].rstrip("/")
    rows = db.execute("SELECT DISTINCT source_url FROM jira_progress").fetchall()
    if not rows:
        raise ValueError("Complete Jira baseline inventory required")
    if any(row[0] != expected for row in rows):
        raise ValueError("Stored Jira evidence belongs to another or unknown endpoint")
    pending = db.execute("SELECT COUNT(*) FROM jira_progress WHERE complete != 1").fetchone()[0]
    if pending:
        raise ValueError("Finish Jira baseline inventory before collecting history")
