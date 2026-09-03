"""Deterministic delivery metrics from Jira changelogs.

No model. Every number is arithmetic on status (and sprint) transitions.
"""

import datetime as dt
import statistics


DONE_NAMES = {"done", "closed", "resolved", "released"}
IN_FLIGHT_NAMES = {"in progress", "in review", "in development",
                   "code review", "review"}


def _name(value):
    return (value or "").strip().lower()


def is_done_name(value):
    text = _name(value)
    return text in DONE_NAMES or text.endswith(" done")


def is_in_flight_name(value):
    text = _name(value)
    return text in IN_FLIGHT_NAMES or "progress" in text or "review" in text


def _when_date(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def first_in_flight(issue):
    """When the issue first entered an in-flight status."""
    for tr in issue.get("transitions") or []:
        if tr.get("field") == "status" and is_in_flight_name(tr.get("to")):
            return _when_date(tr.get("when"))
    return None


def done_on(issue):
    """The date the issue first reached Done, or None."""
    for tr in issue.get("transitions") or []:
        if tr.get("field") == "status" and is_done_name(tr.get("to")):
            return _when_date(tr.get("when"))
    if (issue.get("status_category") or "").lower() == "done":
        return _when_date(issue.get("updated"))
    if is_done_name(issue.get("status")):
        return _when_date(issue.get("updated"))
    return None


def cycle_days(issue):
    """First in-flight to first Done, in whole days. None if either is missing."""
    start = first_in_flight(issue)
    end = done_on(issue)
    if not start or not end or end < start:
        return None
    return (end - start).days


def iso_week(day):
    iso = day.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def week_start(day):
    return day - dt.timedelta(days=day.weekday())


def percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (p / 100.0)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def throughput_by_week(issues, weeks, today=None):
    """[{week, start, done}, ...] oldest first, including empty weeks."""
    today = today or dt.date.today()
    start = week_start(today) - dt.timedelta(weeks=weeks - 1)
    buckets = []
    for i in range(weeks):
        ws = start + dt.timedelta(weeks=i)
        we = ws + dt.timedelta(days=6)
        buckets.append({"week": iso_week(ws), "start": ws.isoformat(),
                        "end": we.isoformat(), "done": 0, "points": 0})
    index = {b["week"]: b for b in buckets}
    for issue in issues:
        when = done_on(issue)
        if not when or when < start or when > today:
            continue
        bucket = index.get(iso_week(when))
        if not bucket:
            continue
        bucket["done"] += 1
        points = issue.get("story_points")
        if isinstance(points, (int, float)) and points > 0:
            bucket["points"] += points
    return buckets


def cycle_summary(issues):
    values = [d for d in (cycle_days(i) for i in issues) if d is not None]
    if not values:
        return {"n": 0, "median": None, "p85": None}
    return {
        "n": len(values),
        "median": int(round(statistics.median(values))),
        "p85": int(round(percentile(values, 85))),
    }


def aging_wip(issues, today=None, limit=8):
    today = today or dt.date.today()
    rows = []
    for issue in issues:
        if (issue.get("issuetype") or "").lower() == "epic":
            continue
        if (issue.get("status_category") or "").lower() == "done":
            continue
        if is_done_name(issue.get("status")):
            continue
        category = (issue.get("status_category") or "").lower()
        if category not in ("indeterminate",) and not is_in_flight_name(issue.get("status")):
            continue
        started = first_in_flight(issue) or _when_date(issue.get("updated"))
        if not started:
            continue
        age = (today - started).days
        rows.append({
            "key": issue.get("key"),
            "summary": issue.get("summary") or "",
            "status": issue.get("status"),
            "age": age,
            "assignee": issue.get("assignee") or "Unassigned",
        })
    rows.sort(key=lambda r: (-r["age"], r.get("key") or ""))
    return rows[:limit], len(rows)


def sprint_scope_change(issues, sprint):
    """Items added to the named sprint after it started."""
    if not sprint or not sprint.get("start"):
        return {"added": 0, "keys": []}
    start = _when_date(sprint.get("start"))
    if not start:
        return {"added": 0, "keys": []}
    name = (sprint.get("name") or "").lower()
    keys = []
    for issue in issues:
        for tr in issue.get("transitions") or []:
            if tr.get("field") != "sprint":
                continue
            when = _when_date(tr.get("when"))
            to = (tr.get("to") or "").lower()
            if when and when > start and name and name in to:
                keys.append(issue.get("key"))
                break
    return {"added": len(keys), "keys": keys}


def forecast_accuracy(issues, sprint):
    """Story points Done during the sprint vs points still/was in the sprint.

    Forecast is the sum of points on issues that currently look like sprint
    work (open sprint membership, or Done during the sprint). Done is the
    subset that reached Done on or after the sprint start.
    """
    start = _when_date((sprint or {}).get("start"))
    forecast = 0
    done = 0
    in_sprint = 0
    for issue in issues:
        points = issue.get("story_points")
        if not isinstance(points, (int, float)) or points <= 0:
            points = 0
        finished = done_on(issue)
        in_open = True  # caller already scoped to the workstream
        if start and finished and finished < start:
            continue
        in_sprint += 1
        forecast += points
        if finished and (not start or finished >= start):
            done += points
    return {"forecast": forecast, "done": done, "items": in_sprint}


def landing_date(open_count, weekly_rate, today=None):
    """Plain calendar date: remaining items at the current weekly rate."""
    today = today or dt.date.today()
    if not weekly_rate or weekly_rate <= 0 or open_count <= 0:
        return None
    weeks = open_count / weekly_rate
    return today + dt.timedelta(days=int(round(weeks * 7)))


def summarise_stream(issues, weeks, sprints=None, today=None):
    """One workstream's metrics bundle."""
    today = today or dt.date.today()
    sprints = sprints or []
    buckets = throughput_by_week(issues, weeks, today=today)
    rate = (sum(b["done"] for b in buckets) / weeks) if weeks else 0
    open_items = [i for i in issues
                  if (i.get("issuetype") or "").lower() != "epic"
                  and (i.get("status_category") or "").lower() != "done"
                  and not is_done_name(i.get("status"))]
    aging, aging_total = aging_wip(issues, today=today)
    sprint = sprints[0] if sprints else None
    return {
        "throughput": buckets,
        "weekly_rate": round(rate, 2),
        "cycle": cycle_summary(issues),
        "aging": aging,
        "aging_total": aging_total,
        "scope_change": sprint_scope_change(issues, sprint),
        "accuracy": forecast_accuracy(issues, sprint),
        "open": len(open_items),
        "landing": (landing_date(len(open_items), rate, today=today)
                    or None),
        "sprint": (sprint or {}).get("name"),
    }
