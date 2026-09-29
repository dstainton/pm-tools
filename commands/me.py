"""`pm me` — one person's work, ignoring role.

No window is a snapshot of open issues as they stand today. A window
(`--sprint`, `--since`, `--days`, or `--summary`) is what finished and what
is still open in that stretch. Neither run moves the weekly-report memory.
"""

import datetime as dt
import sys

from core import blocked, citations, comments, output, queries, render, sources, terminal, workstreams
from core import window as window_core


_OUTSIDE = "Outside your workstreams"


def _projects(cfg):
    found = []
    project = (cfg.get("jira") or {}).get("project")
    if project:
        found.append(project)
    for ws in cfg.get("workstreams") or []:
        extra = ws.get("project")
        if extra and extra not in found:
            found.append(extra)
    return found


def _person(cfg, args):
    """The signed-in user, or someone else when a product manager asks."""
    from core import audience
    who = (getattr(args, "who", None) or "").strip()
    if not who:
        return None
    if audience.resolve_shape(cfg, args) != "pm":
        sys.exit("A report about someone else is for the product manager. "
                 "pm me shows your own work.")
    jira = cfg.get("jira") or cfg
    person = sources.resolve_assignee(jira, who)
    if not person or not person.get("accountId"):
        sys.exit(f"No Jira user matches {who}.")
    return person


def _assignee_clause(cfg, person):
    if person and person.get("accountId"):
        account = str(person["accountId"]).replace('"', "")
        return f'assignee = "{account}"'
    return queries.render(cfg, "assignee.me")


def _project_clause(cfg):
    projects = _projects(cfg)
    if not projects:
        sys.exit("No Jira project is configured.")
    joined = ", ".join(projects)
    return f"project in ({joined})"


def _fetch(cfg, jql):
    jira = cfg.get("jira") or cfg
    return sources.fetch_jira_detailed(jira, jql)


def _in_open_sprint(cfg, clause, project_clause):
    sprint = queries.render(cfg, "sprint.open")
    jql = f"{clause} AND {project_clause} AND {sprint}"
    try:
        return set(sources.fetch_jira_keys(cfg.get("jira") or cfg, jql))
    except Exception:                              # noqa: BLE001
        return set()


def _bucket(cfg, issue):
    components = {str(name).strip().lower()
                  for name in (issue.get("components") or []) if str(name).strip()}
    streams = cfg.get("_workstreams") or cfg.get("workstreams") or []
    for ws in streams:
        names = {str(name).strip().lower() for name in workstreams.components_of(ws)}
        if components & names:
            return ws
    return None


def _days_since(issue, today):
    updated = sources.parse_timestamp(issue.get("updated"))
    if updated is None:
        return None
    return (dt.datetime(today.year, today.month, today.day, tzinfo=dt.timezone.utc)
            - updated.astimezone(dt.timezone.utc)).days


def _overdue(issue, today):
    due = str(issue.get("due_date") or "")[:10]
    try:
        day = dt.date.fromisoformat(due)
    except ValueError:
        return False
    return day < today


def _key(issue):
    return render.markdown_link(issue.get("key"), issue.get("url"))


def _epic_heading(cfg, epic, rows):
    """An Epic key links to the Epic. The placeholder heading stays text."""
    if not citations.is_issue_key(epic):
        return epic
    sample = next((row.get("url") for row in rows if row.get("url")), "")
    return render.markdown_link(epic, render.browse_url(cfg, epic, sample))


def _line(issue, today, sprint_name, in_sprint):
    bits = [_key(issue), issue.get("summary") or ""]
    detail = [issue.get("issuetype") or "", issue.get("status") or ""]
    if in_sprint and sprint_name:
        detail.append(sprint_name)
    due = str(issue.get("due_date") or "")[:10]
    if due:
        detail.append(f"due {due}")
    age = _days_since(issue, today)
    if age is not None:
        detail.append(f"updated {age}d ago")
    if blocked.is_blocked(issue):
        detail.append("blocked")
    return "- " + " — ".join(part for part in bits if part) + " (" + ", ".join(
        part for part in detail if part) + ")"


def _group(cfg, issues):
    """{workstream abbrev or outside: {epic key: [issues]}}."""
    grouped = {}
    order = []
    for issue in issues:
        ws = _bucket(cfg, issue)
        label = ws["abbrev"] if ws else _OUTSIDE
        title = ws.get("name") if ws else _OUTSIDE
        if label not in grouped:
            grouped[label] = {"title": title, "epics": {}}
            order.append(label)
        epic = issue.get("epic") or "Not under an Epic"
        grouped[label]["epics"].setdefault(epic, []).append(issue)
    return [(label, grouped[label]) for label in order]


def _write(cfg, args, name, text):
    path = output.place(cfg, name, getattr(args, "out", None))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    terminal.show(text, args)
    print()
    print(f"Written to {path}")


def _subject(person):
    if person and person.get("displayName"):
        return person["displayName"]
    return "Your"


def render_snapshot(cfg, issues, person, today, sprint):
    in_sprint = set()
    sprint_name = ""
    sprint_goal = ""
    if sprint:
        sprint_name = sprint.get("name") or ""
        sprint_goal = (sprint.get("goal") or "").strip()
        in_sprint = set(sprint.get("keys") or [])
    title = _subject(person)
    possessive = title if title != "Your" else "Your"
    heading = f"# {title}'s work" if title != "Your" else "# Your work"
    lines = [
        heading,
        f"_{today.isoformat()}_",
        "",
        "Snapshot. This is where the work stands, not what changed since last time.",
        "",
    ]
    if sprint_name and any((issue.get("key") in in_sprint) for issue in issues):
        lines.append(f"Open Sprint: {sprint_name}")
        if sprint_goal:
            lines.append("")
            lines.append(sprint_goal)
        lines.append("")
    open_n = len(issues)
    progressing = sum(1 for issue in issues
                      if (issue.get("status_category") or "") == "indeterminate")
    blocked_n = sum(1 for issue in issues if blocked.is_blocked(issue))
    overdue_n = sum(1 for issue in issues if _overdue(issue, today))
    lines.append(
        f"{open_n} open, {progressing} in progress, {blocked_n} blocked, "
        f"{overdue_n} overdue.")
    lines.append("")
    if not issues:
        lines.append("_No open issues._")
        lines.append("")
        return "\n".join(lines)
    for label, block in _group(cfg, issues):
        lines.append(f"## {block['title']}")
        lines.append("")
        for epic, rows in block["epics"].items():
            lines.append(f"### {_epic_heading(cfg, epic, rows)}")
            lines.append("")
            for issue in rows:
                lines.append(_line(issue, today, sprint_name, issue.get("key") in in_sprint))
            lines.append("")
    return "\n".join(lines)


def _summary_default(cfg, args):
    """Fill a window from `me.summary` only when `--summary` was passed alone."""
    if getattr(args, "since", None) or getattr(args, "days", None) or getattr(args, "sprint", None):
        return
    if not getattr(args, "summary", False):
        return
    choice = (cfg.get("me") or {}).get("summary", "sprint")
    if choice == "sprint" or choice is None:
        args.sprint = "open"
    else:
        args.days = int(choice)


def _wants_summary(args):
    return bool(getattr(args, "since", None) or getattr(args, "days", None)
                or getattr(args, "sprint", None) or getattr(args, "summary", False))


def render_summary(cfg, open_issues, finished, person, window, today):
    start = window.get("start")
    start_day = start if isinstance(start, dt.date) else today
    title = _subject(person)
    heading = f"# {title}'s work" if title != "Your" else "# Your work"
    lines = [
        heading,
        f"_{window.get('label') or 'window'} · {today.isoformat()}_",
        "",
        "## Finished",
        "",
    ]
    if finished:
        for _label, block in _group(cfg, finished):
            lines.append(f"### {block['title']}")
            lines.append("")
            for epic, rows in block["epics"].items():
                lines.append(f"#### {_epic_heading(cfg, epic, rows)}")
                lines.append("")
                for issue in rows:
                    lines.append(f"- {_key(issue)} — {issue.get('summary') or ''}")
                lines.append("")
    else:
        lines.append("_Nothing finished in this window._")
        lines.append("")
    updated = []
    for issue in open_issues:
        stamp = sources.parse_timestamp(issue.get("updated"))
        if stamp is not None and stamp.date() >= start_day:
            updated.append(issue)
    lines.append("## Updated and still open")
    lines.append("")
    if updated:
        for issue in updated:
            lines.append(f"- {_key(issue)} — {issue.get('summary') or ''} "
                         f"({issue.get('status') or ''})")
    else:
        lines.append("_Nothing still open was updated in this window._")
    lines.append("")
    lines.append("## Still open")
    lines.append("")
    if not open_issues:
        lines.append("_Nothing open._")
    else:
        for issue in open_issues:
            lines.append(f"- {_key(issue)} — {issue.get('summary') or ''} "
                         f"({issue.get('status') or ''})")
    lines.append("")
    notes = []
    for issue in list(finished) + list(open_issues):
        for line in issue.get("comments") or []:
            notes.append(f"- {_key(issue)} — {line}")
    if notes:
        lines.append("## Comments")
        lines.append("")
        lines.extend(notes)
        lines.append("")
    return "\n".join(lines)


def run(cfg, args):
    person = _person(cfg, args)
    clause = _assignee_clause(cfg, person)
    project_clause = _project_clause(cfg)
    today = dt.date.today()
    jira = cfg.get("jira") or cfg
    _summary_default(cfg, args)
    if not _wants_summary(args):
        status = queries.render(cfg, "status.open")
        issues = _fetch(cfg, f"{clause} AND {status} AND {project_clause}")
        keys = _in_open_sprint(cfg, clause, project_clause)
        sprints = []
        try:
            project = _projects(cfg)[0]
            sprints = sources.fetch_active_sprints(jira, project)
        except Exception:                              # noqa: BLE001
            sprints = []
        current = dict(sprints[0]) if sprints else {}
        if current:
            current["keys"] = keys
        text = render_snapshot(cfg, issues, person, today, current or None)
        _write(cfg, args, f"me_snapshot_{today.isoformat()}.md", text)
        return

    try:
        window = window_core.resolve(
            cfg, args, default_start=None, projects=_projects(cfg), today=today)
    except window_core.WindowError as exc:
        sys.exit(str(exc))
    status_open = queries.render(cfg, "status.open")
    open_issues = _fetch(cfg, f"{clause} AND {status_open} AND {project_clause}")
    start = window["start"].isoformat()
    done = queries.render(cfg, "status.done")
    since = queries.render(cfg, "release_notes.since", since=start)
    end = window["end"].isoformat() if window.get("end") else ""
    finished_jql = f"{clause} AND {done} AND {since} AND {project_clause}"
    if end:
        finished_jql += f' AND resolved <= "{end}"'
    finished = _fetch(cfg, finished_jql)
    cutoff = dt.datetime.combine(window["start"], dt.time.min, tzinfo=dt.timezone.utc)
    comments.attach(cfg, jira, list(open_issues) + list(finished), cutoff, author=True)
    text = render_summary(cfg, open_issues, finished, person, window, today)
    if window.get("sprint_id"):
        stamp = str(window["sprint_id"])
    else:
        stamp = start
    _write(cfg, args, f"me_summary_{stamp}_{today.isoformat()}.md", text)
