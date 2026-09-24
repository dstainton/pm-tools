"""`pm show KEY` — one issue, on screen.

The cheapest missing command: status, assignee, dates, and the url,
without opening a browser or writing a file.
"""

import sys

from core import render
from core import sources


def run(cfg, args):
    key = (getattr(args, "key", None) or "").strip()
    if not key:
        sys.exit("Which issue? e.g.  pm show APS-30")
    jql = f"key = {key}"
    issues = sources.fetch_jira_detailed(cfg["jira"], jql)
    issue = next((item for item in issues if item.get("key") == key), None)
    if issue is None and issues:
        issue = issues[0]
    if issue is None:
        sys.exit(f"No issue {key}.")
    plain = render.plain_requested(args)
    links = render.terminal_links() and not plain
    url = issue.get("url") or ""
    shown = render.issue_cell(issue.get("key"), url, len(issue.get("key") or ""), links)
    lines = [
        shown,
        f"Summary: {issue.get('summary') or ''}",
        f"Status: {issue.get('status') or ''}",
        f"Assignee: {issue.get('assignee') or 'Unassigned'}",
        f"Type: {issue.get('issuetype') or ''}",
        f"Due: {issue.get('due_date') or 'none'}",
        f"URL: {url}",
    ]
    text = "\n".join(lines)
    if getattr(args, "json", False):
        import json
        payload = {k: issue.get(k) for k in (
            "key", "summary", "status", "assignee", "issuetype",
            "due_date", "url", "story_points")}
        print(json.dumps(payload, indent=2, default=str))
        return
    print(text)
