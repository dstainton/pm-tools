"""One window for the commands that narrate a period.

A Sprint is a membership (`sprint = 1234`) and a date range. Callers that
pass no flag keep today's behaviour: since the last run of that command.
An explicit window is a read; it must not advance that memory.
"""

import datetime as dt
import re

from core import sources


_NUMBER = re.compile(r"\d+")


class WindowError(Exception):
    """The user named a window we could not resolve."""


def parse_date(value):
    text = str(value or "")[:10]
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def _explicit(args):
    since = getattr(args, "since", None) if args is not None else None
    days = getattr(args, "days", None) if args is not None else None
    weeks = getattr(args, "weeks", None) if args is not None else None
    sprint = getattr(args, "sprint", None) if args is not None else None
    # metrics uses --sprint as a boolean today. A string is a named Sprint.
    if sprint is True:
        sprint = ""
    if sprint is False or sprint is None:
        sprint = None
    return since, days, weeks, sprint


def is_explicit(args):
    since, days, weeks, sprint = _explicit(args)
    if sprint is not None:
        return True
    return bool(since) or days not in (None, 1) and days is not None or (
        weeks not in (None, 8) and weeks is not None)


def resolve_sprint(sprints, token):
    """Match a number or a name. Ambiguous answers list the candidates."""
    token = "" if token is None else str(token).strip()
    if not token or token.lower() == "open":
        active = [s for s in sprints if (s.get("state") or "active") == "active"]
        if not active:
            raise WindowError("No open Sprint.")
        return active[0]
    if token.lower() == "last":
        closed = [s for s in sprints if s.get("state") == "closed" and s.get("end")]
        closed.sort(key=lambda s: s.get("end") or "")
        if not closed:
            raise WindowError("No closed Sprint to use as last.")
        return closed[-1]
    want = token.lower()
    number = token if token.isdigit() else None
    hits = []
    for sprint in sprints:
        name = (sprint.get("name") or "")
        if want == name.lower():
            hits.append(sprint)
            continue
        if number and number in _NUMBER.findall(name):
            hits.append(sprint)
            continue
        if number and str(sprint.get("id") or "") == number:
            hits.append(sprint)
    # Prefer a name that ends with the number (APS SP138) over a looser hit.
    if number and len(hits) > 1:
        tight = [s for s in hits if (s.get("name") or "").lower().endswith(number)
                 or (s.get("name") or "").lower().endswith("sp" + number)]
        if len(tight) == 1:
            hits = tight
    if not hits:
        names = ", ".join(s.get("name") or str(s.get("id")) for s in sprints[:12])
        raise WindowError(f"No Sprint matches {token}. Available: {names}.")
    if len(hits) > 1:
        names = ", ".join(s.get("name") or str(s.get("id")) for s in hits[:12])
        raise WindowError(f"Sprint {token} is ambiguous. Available: {names}.")
    return hits[0]


def resolve(cfg, args=None, *, default_start=None, default_days=None,
            projects=None, today=None):
    """Return start, end, jql, label, and whether the user named a window.

    `default_start` is the command's existing memory (last report, last
    brief). `default_days` covers `pm daily` and `pm metrics`.
    """
    today = today or dt.date.today()
    since, days, weeks, sprint_token = _explicit(args)
    explicit = False
    start = default_start
    end = today
    jql = None
    label = "since last run"

    if sprint_token is not None:
        explicit = True
        found = []
        for project in projects or []:
            found.extend(sources.fetch_sprints(
                cfg.get("jira") or cfg, project,
                states=("active", "closed", "future")))
        chosen = resolve_sprint(found, "" if sprint_token is True else sprint_token)
        start = parse_date(chosen.get("start")) or today
        end = parse_date(chosen.get("end")) or today
        sprint_id = chosen.get("id")
        jql = f"sprint = {int(sprint_id)}" if sprint_id is not None else None
        label = chosen.get("name") or "Sprint"
    elif since:
        explicit = True
        start = parse_date(since)
        if start is None:
            raise WindowError(f"--since needs YYYY-MM-DD (got {since!r}).")
        label = f"since {start.isoformat()}"
    elif weeks not in (None,):
        # metrics default is 8. Only an explicit flag marks the run read-only
        # when the caller says the flag was passed. `weeks` on the namespace
        # is always set for metrics, so callers pass default_days instead
        # and leave weeks None unless the user overrode it.
        explicit = True
        start = today - dt.timedelta(days=int(weeks) * 7)
        label = f"last {int(weeks)} weeks"
    elif days is not None and default_days is not None and int(days) != int(default_days):
        explicit = True
        start = today - dt.timedelta(days=int(days))
        label = f"last {int(days)} days"
    elif days is not None and default_start is None and default_days is None:
        explicit = True
        start = today - dt.timedelta(days=int(days))
        label = f"last {int(days)} days"
    elif start is None and default_days:
        start = today - dt.timedelta(days=int(default_days))
        label = f"last {int(default_days)} days"

    if start is None:
        start = today - dt.timedelta(days=7)
        label = "last 7 days"
    return {
        "start": start,
        "end": end,
        "jql": jql,
        "label": label,
        "explicit": explicit,
        "sprint_id": sprint_id if sprint_token is not None else None,
    }


def file_stamp(window, today=None):
    """Name a windowed file after the window so two runs do not collide."""
    today = today or dt.date.today()
    if not window or not window.get("explicit"):
        return today.isoformat()
    start = window.get("start")
    label = re.sub(r"[^A-Za-z0-9]+", "-", window.get("label") or "window").strip("-")
    if hasattr(start, "isoformat"):
        return f"{start.isoformat()}_{label}"[:80]
    return label[:80] or today.isoformat()
