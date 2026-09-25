"""Epic facts for a workstream: parent walk, child counts, and the signal rule."""

import datetime as dt

from core import blocked, queries, sources, workstreams


def parent_map(cfg, items, epic_types, max_depth=3):
    """{key: parent_key} plus {key: raw fields} for fetched ancestors."""
    parents = {}
    fields_by_key = {}
    for item in items:
        key = item.get("key") or item.get("uid")
        if not key:
            continue
        parents[key] = item.get("parent")
        fields_by_key[key] = {
            "issuetype": item.get("issuetype"),
            "summary": item.get("summary"),
            "status": item.get("status"),
            "status_category": item.get("status_category"),
            "duedate": item.get("due"),
            "updated": item.get("updated"),
        }
    missing = [key for key, parent in parents.items()
               if parent and parent not in parents]
    depth = 0
    while missing and depth < max_depth:
        depth += 1
        raws = sources.fetch_issues_by_key(cfg.get("jira") or cfg, missing, [
            "summary", "status", "issuetype", "parent", "duedate", "updated", "labels"])
        missing = []
        for raw in raws:
            key = raw.get("key")
            f = raw.get("fields") or {}
            parent = (f.get("parent") or {}).get("key")
            parents[key] = parent
            status = f.get("status") or {}
            fields_by_key[key] = {
                "issuetype": (f.get("issuetype") or {}).get("name") or "",
                "summary": f.get("summary") or "",
                "status": status.get("name") or "",
                "status_category": (status.get("statusCategory") or {}).get("key") or "",
                "duedate": f.get("duedate") or "",
                "updated": f.get("updated") or "",
            }
            if parent and parent not in parents:
                missing.append(parent)
    return parents, fields_by_key


def epic_of(key, parents, types_by_key, epic_types):
    """Walk up until an issue whose type is in epic_types. None if none."""
    names = {str(t).lower() for t in epic_types}
    seen = set()
    current = key
    while current and current not in seen:
        seen.add(current)
        if str(types_by_key.get(current) or "").lower() in names:
            return current
        current = parents.get(current)
    return None


def assign(items, parents, types_by_key, epic_types):
    """Set item['epic'] on every Jira item (None when not under an Epic)."""
    for item in items:
        if item.get("source") != "Jira":
            continue
        key = item.get("key") or item.get("uid")
        item["epic"] = epic_of(key, parents, types_by_key, epic_types)
    return items


def _child_row(raw):
    f = raw.get("fields") or {}
    status = f.get("status") or {}
    return {
        "key": raw.get("key"),
        "parent": (f.get("parent") or {}).get("key"),
        "issuetype": (f.get("issuetype") or {}).get("name") or "",
        "status": status.get("name") or "",
        "status_category": (status.get("statusCategory") or {}).get("key") or "",
        "labels": list(f.get("labels") or []),
    }


def child_counts(cfg, epic_keys, blocked_cfg):
    """Direct children only. {epic_key: {total, done, in_progress, blocked}}."""
    counts = {key: {"total": 0, "done": 0, "in_progress": 0, "blocked": 0}
              for key in epic_keys}
    keys = [key for key in epic_keys if key]
    jira = cfg.get("jira") or cfg
    for start in range(0, len(keys), 100):
        chunk = keys[start:start + 100]
        jql = queries.render(cfg, "epics.children", keys=chunk)
        for raw in sources.search_issues(
                jira, jql, fields=["status", "issuetype", "parent", "labels"],
                max_items=0):
            row = _child_row(raw)
            if str(row["issuetype"]).lower() == "sub-task":
                continue
            parent = row["parent"]
            if parent not in counts:
                continue
            bucket = counts[parent]
            bucket["total"] += 1
            if row["status_category"] == "done":
                bucket["done"] += 1
            elif row["status_category"] == "indeterminate":
                bucket["in_progress"] += 1
            if blocked.is_blocked(row, blocked_cfg):
                bucket["blocked"] += 1
    return counts


def signal(epic, counts, window_start, today, at_risk_due_days, updated_in_window):
    """(word, reason). First match wins: Done, At risk, No movement, Not started, On track."""
    category = (epic.get("status_category") or "").lower()
    due = epic.get("due") or ""
    due_date = None
    if due:
        try:
            due_date = dt.date.fromisoformat(str(due)[:10])
        except ValueError:
            due_date = None
    total = counts.get("total") or 0
    done = counts.get("done") or 0
    in_progress = counts.get("in_progress") or 0
    blocked_n = counts.get("blocked") or 0
    if category == "done":
        return "Done", "status category is done"
    reasons = []
    if blocked_n:
        reasons.append(f"{blocked_n} blocked")
    if due_date and due_date < today:
        reasons.append("due date has passed")
    if due_date and today <= due_date <= today + dt.timedelta(days=int(at_risk_due_days or 14)):
        if total and done * 2 < total:
            reasons.append("under half done within the due window")
    if reasons:
        return "At risk", "; ".join(reasons)
    if not updated_in_window:
        return "No movement", "nothing updated in the window"
    if in_progress == 0 and done == 0 and category == "new":
        return "Not started", "no child has started"
    return "On track", "work is moving"


def _parse_day(value):
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def build(cfg, ws, items, window, prev_changes):
    """Epic dicts for this workstream, At risk first, then by key."""
    epic_types = workstreams.membership_settings(cfg)["epic_types"]
    jira_items = [it for it in items if it.get("source") == "Jira"]
    parents, fields_by_key = parent_map(cfg, jira_items, epic_types)
    types = {key: (fields.get("issuetype") or "") for key, fields in fields_by_key.items()}
    assign(jira_items, parents, types, epic_types)

    owned = set(workstreams.get_epic_keys(cfg, ws) or [])
    keys = set()
    for item in jira_items:
        if item.get("epic"):
            keys.add(item["epic"])
        if str(item.get("issuetype") or "").lower() in {t.lower() for t in epic_types}:
            keys.add(item.get("key"))
    window_start = (window or {}).get("start")
    if window_start and owned:
        base = workstreams.membership_jql(cfg, ws, "epics")
        if base:
            jql = queries.render(cfg, "epics.resolved", base=base, since=window_start.isoformat())
            for raw in sources.search_issues(cfg.get("jira") or cfg, jql, fields=["summary", "status", "issuetype", "duedate", "updated"], max_items=0):
                keys.add(raw.get("key"))
                if raw.get("key") not in fields_by_key:
                    f = raw.get("fields") or {}
                    status = f.get("status") or {}
                    fields_by_key[raw["key"]] = {
                        "issuetype": (f.get("issuetype") or {}).get("name") or "",
                        "summary": f.get("summary") or "",
                        "status": status.get("name") or "",
                        "status_category": (status.get("statusCategory") or {}).get("key") or "",
                        "duedate": f.get("duedate") or "",
                        "updated": f.get("updated") or "",
                    }

    counts = child_counts(cfg, sorted(k for k in keys if k), cfg)
    today = dt.date.today()
    days = ((cfg.get("audiences") or {}).get("leadership") or {}).get("at_risk_due_days", 14)
    changed_keys = {it.get("key") for it, _old in (prev_changes or ([], []))[1]} if False else set()
    _new, changed, _dropped = prev_changes or ([], [], [])
    changed_keys = {it.get("key") for it, _old in changed}

    rows = []
    for key in keys:
        if not key:
            continue
        facts = fields_by_key.get(key) or {}
        updated = _parse_day(facts.get("updated"))
        child_updated = False
        for item in jira_items:
            if item.get("epic") == key and _parse_day(item.get("updated")) and window_start:
                if _parse_day(item.get("updated")) >= window_start:
                    child_updated = True
        epic_updated = bool(updated and window_start and updated >= window_start)
        bucket = counts.get(key) or {"total": 0, "done": 0, "in_progress": 0, "blocked": 0}
        epic = {
            "key": key,
            "summary": facts.get("summary") or key,
            "status": facts.get("status") or "",
            "status_category": facts.get("status_category") or "",
            "due": facts.get("duedate") or "",
            "children_total": bucket["total"],
            "children_done": bucket["done"],
            "children_in_progress": bucket["in_progress"],
            "blocked": bucket["blocked"],
            "in_scope": key in owned,
            "items": [it for it in jira_items if it.get("epic") == key],
            "moved": [it for it in jira_items if it.get("epic") == key and it.get("key") in changed_keys],
            "pages": [],
        }
        word, reason = signal(
            epic, bucket, window_start, today, days,
            epic_updated or child_updated or bool(epic["moved"]))
        epic["signal"] = word
        epic["signal_reason"] = reason
        rows.append(epic)

    order = {"At risk": 0, "Done": 1, "No movement": 2, "Not started": 3, "On track": 4}
    rows.sort(key=lambda row: (order.get(row["signal"], 9), row["key"] or ""))
    loose = [it for it in jira_items if not it.get("epic")
             and str(it.get("issuetype") or "").lower() not in {t.lower() for t in epic_types}]
    if loose:
        rows.append({"key": None, "summary": "Not under an Epic", "items": loose,
                     "moved": [], "pages": [], "in_scope": True, "signal": ""})
    return rows
