"""Windowed Jira comments for the commands that narrate a period.

`pm report`, `pm brief`, `pm daily`, `pm release-notes`, and `pm triage`
read comments inside the window that command already uses. The whole
thread is not kept. An issue is asked for comments only when its updated
time is inside the window, because a new comment moves that timestamp.
"""

import datetime as dt

from core import sources


DEFAULTS = {
    "enabled": True,
    "max_per_issue": 3,
    "max_issues": 25,
    "excerpt_chars": 240,
    "report_days": 7,
    "section_chars": 6000,
}


def settings(cfg):
    """The `comments:` block, with defaults for anything unset."""
    block = cfg.get("comments") if isinstance(cfg.get("comments"), dict) else {}
    out = dict(DEFAULTS)
    for key, default in DEFAULTS.items():
        if key not in block or block[key] is None:
            continue
        value = block[key]
        if key == "enabled":
            out[key] = bool(value)
            continue
        try:
            out[key] = max(0, int(value))
        except (TypeError, ValueError):
            out[key] = default
    return out


def comment_text(comment):
    """Plain text of one comment body."""
    if not isinstance(comment, dict):
        return ""
    return sources.adf_to_text(comment.get("body"))


def mention_ids(comment):
    """accountIds on ADF mention nodes. Plain text has none."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "mention":
                account = str((node.get("attrs") or {}).get("id") or "")
                if account:
                    found.append(account)
            for child in node.get("content") or []:
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    if isinstance(comment, dict):
        walk(comment.get("body"))
    return found


def author_name(comment):
    author = (comment or {}).get("author") or {}
    return author.get("displayName") or author.get("name") or "Someone"


def format_line(comment, excerpt_chars):
    """`2026-09-22 Dana: the excerpt`, or '' when the body is empty."""
    text = sources.short(comment_text(comment), excerpt_chars or 0)
    if not text:
        return ""
    created = sources.parse_timestamp(comment.get("created"))
    if created:
        when = created.astimezone(dt.timezone.utc).date().isoformat()
    else:
        when = "undated"
    return f"{when} {author_name(comment)}: {text}"


def report_cutoff(snapshot, opts, now=None):
    """When the last report ran, or `report_days` before now on a first run.

    A snapshot from before this feature has items and no timestamp. That
    run uses `report_days` as well.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    raw = snapshot.get("_ran_at") if isinstance(snapshot, dict) else None
    parsed = sources.parse_timestamp(raw) if raw else None
    if parsed:
        return parsed
    days = int(opts.get("report_days") or 0)
    return now - dt.timedelta(days=days)


def audience_cutoff(last, opts, now=None):
    """When this audience was last briefed, or `report_days` before now."""
    now = now or dt.datetime.now(dt.timezone.utc)
    parsed = sources.parse_timestamp(last) if last else None
    if parsed:
        return parsed
    days = int(opts.get("report_days") or 0)
    return now - dt.timedelta(days=days)


def _issue_key(issue):
    return (issue or {}).get("key") or (issue or {}).get("uid")


def _updated_inside(issue, cutoff):
    if cutoff is None:
        return True
    updated = sources.parse_timestamp(issue.get("updated"))
    if updated is None:
        return False
    return updated >= cutoff


def load_for_issues(jira_cfg, issues, cutoff, opts):
    """`{key: [comment lines]}` for issues updated inside the window.

    At most `max_issues` issues are asked, newest update first. An issue
    whose comments are all older than the cutoff is left out.
    """
    if not opts.get("enabled"):
        return {}
    per_issue = int(opts.get("max_per_issue") or 0)
    max_issues = int(opts.get("max_issues") or 0)
    if per_issue <= 0 or max_issues <= 0:
        return {}
    excerpt = int(opts.get("excerpt_chars") or 0)
    candidates = [issue for issue in issues if _updated_inside(issue, cutoff)]
    candidates.sort(
        key=lambda issue: sources.parse_timestamp(issue.get("updated"))
        or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
        reverse=True)
    found = {}
    asked = 0
    for issue in candidates:
        if asked >= max_issues:
            break
        key = _issue_key(issue)
        if not key:
            continue
        asked += 1
        try:
            raw = sources.fetch_comments(
                jira_cfg, key, cutoff=cutoff, limit=per_issue)
        except Exception:                              # noqa: BLE001
            continue
        lines = []
        for comment in raw:
            line = format_line(comment, excerpt)
            if line:
                lines.append(line)
        if lines:
            found[key] = lines
    return found


def attach(cfg, jira_cfg, issues, cutoff):
    """Set `issue['comments']` to the formatted lines, or an empty list."""
    opts = settings(cfg)
    found = load_for_issues(jira_cfg, issues, cutoff, opts)
    for issue in issues:
        key = _issue_key(issue)
        issue["comments"] = found.get(key) or []
    return opts
