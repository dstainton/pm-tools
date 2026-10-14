"""Pure, deterministic analysis of a Phase 1A open-issue inventory.

No Jira requests, model calls, persistence, or wall-clock reads. Results are
review signals, not implementation priorities or proof that an issue is obsolete.
"""

import datetime as dt
from collections import Counter


AGE_BANDS = ("0-30", "31-90", "91-180", "181-365", "366+", "unknown")


def _day(value):
    if not value:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _age(value, today):
    day = _day(value)
    return max(0, (today - day).days) if day else None


def _band(age):
    if age is None:
        return "unknown"
    for end, name in ((30, "0-30"), (90, "31-90"),
                      (180, "91-180"), (365, "181-365")):
        if age <= end:
            return name
    return "366+"


def _issue_type(issue):
    return str(issue.get("issuetype") or "Unknown")


def _status(issue):
    return str(issue.get("status_category") or "unknown").lower()


def _claims(issue, claims):
    return sorted(set(claims.get(issue.get("key"), ()) or ()))


def analyze(inventory, today, claims=None, rules=None):
    """Analyze normalized open issues with a supplied date and ownership map.

    `claims` maps Jira issue keys to configured workstream abbreviations.
    When absent, ownership coverage is unknown, not zero unclaimed issues.
    `rules` overrides optional age and issue-type expectations.

    Returns self-contained facts and per-issue finding evidence. A partial
    inventory is never labelled as a complete assessment.
    """
    today = _day(today)
    if today is None:
        raise ValueError("today must be an ISO date or date instance")
    rules = rules or {}
    stale_days = int(rules.get("stale_days", 30))
    epic_types = {str(x).lower() for x in rules.get("epic_types", ("Epic",))}
    parent_types = {str(x).lower() for x in rules.get(
        "parent_types", ("Story", "Bug", "Sub-task", "Subtask"))}
    estimate_types = {str(x).lower() for x in rules.get("estimate_types", ("Story",))}
    criteria_types = {str(x).lower() for x in rules.get("criteria_types", ("Story", "Bug"))}

    status = inventory.get("status") or "failed"
    rows = list(inventory.get("issues") or [])
    types, statuses, ages_created, ages_updated = Counter(), Counter(), Counter(), Counter()
    findings = []
    for issue in rows:
        key = issue.get("key") or ""
        itype = _issue_type(issue)
        category = _status(issue)
        types[itype] += 1
        statuses[category] += 1
        created_age = _age(issue.get("created"), today)
        updated_age = _age(issue.get("updated"), today)
        ages_created[_band(created_age)] += 1
        ages_updated[_band(updated_age)] += 1
        evidence = {"key": key, "url": issue.get("url") or "",
                    "created_age_days": created_age, "updated_age_days": updated_age}
        def flag(rule, detail):
            findings.append(dict(evidence, rule=rule, detail=detail))

        if not issue.get("components"):
            flag("missing-component", "No Jira component assigned")
        if not issue.get("labels"):
            flag("missing-labels", "No Jira labels; labels may be optional")
        if not issue.get("description"):
            flag("missing-description", "No description available")
        if not issue.get("assignee") or issue["assignee"] == "Unassigned":
            flag("unassigned-person", "No individual assignee")
        lower_type = itype.lower()
        if lower_type in parent_types and not issue.get("epic"):
            flag("missing-parent", "No parent/Epic link available")
        if lower_type in estimate_types and issue.get("story_points") in (None, ""):
            flag("missing-estimate", "Estimate is not recorded")
        if lower_type in criteria_types and not issue.get("acceptance_criteria"):
            flag("missing-criteria-field", "No acceptance criteria in the configured field; description may contain them")
        if category == "indeterminate" and updated_age is not None and updated_age > stale_days:
            flag("stalled-active", f"No Jira update for {updated_age} days while in progress")
        due = _day(issue.get("due_date"))
        if due and due < today:
            flag("overdue", f"Due date {due.isoformat()} has passed")
        if claims is not None:
            owners = _claims(issue, claims)
            if not owners:
                flag("unclaimed-workstream", "No configured workstream claims this issue")
            elif len(owners) > 1:
                flag("multiple-workstreams", "Claimed by: " + ", ".join(owners))

    counts = Counter(item["rule"] for item in findings)
    return {
        "project": inventory.get("project"), "today": today.isoformat(),
        "inventory_status": status, "complete": status == "complete",
        "inventory_reason": inventory.get("reason") or "",
        "count": len(rows), "by_type": dict(sorted(types.items())),
        "by_status_category": dict(sorted(statuses.items())),
        "created_age_bands": {band: ages_created[band] for band in AGE_BANDS},
        "updated_age_bands": {band: ages_updated[band] for band in AGE_BANDS},
        "ownership_evaluated": claims is not None,
        "finding_counts": dict(sorted(counts.items())),
        "findings": sorted(findings, key=lambda x: (x["rule"], x["key"])),
    }
