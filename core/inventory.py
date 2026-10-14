"""Read-only, project-wide Jira inventory for Phase 1A.

This module does not generate assessments or modify issues.
"""

import datetime as dt

from core import queries, sources


def open_issues(cfg, project):
    """Return normalized open issues and honest retrieval metadata.

    The query is project-based, never workstream-based. A terminal continuation
    token establishes completion for the Jira result stream. Duplicate keys,
    malformed records, and interrupted paging yield partial results.
    """
    project = str(project or "").strip()
    if not project:
        return {"project": project, "jql": "", "issues": [], "count": 0,
                "status": "failed", "reason": "project is required",
                "pages": 0, "retrieved_at": dt.datetime.now(
                    dt.timezone.utc).isoformat(), "missing_config": []}

    jql = queries.render(cfg, "coverage.open_in_project",
                         project=project)
    jira = cfg["jira"]
    fields = ["summary", "status", "issuetype", "components", "assignee",
              "labels", "duedate", "updated", "created", "description", "parent"]
    optional = ("story_points_field", "start_date_field",
                "acceptance_criteria_field", "epic_link_field")
    missing_config = [key for key in optional[:3] if not jira.get(key)]
    for key in optional:
        field = jira.get(key)
        if field and field not in fields:
            fields.append(field)

    result = sources.search_issues(
        jira, jql, fields=fields, expand="changelog",
        max_items=0, with_metadata=True)
    unique, seen, invalid, duplicates = [], set(), 0, 0
    for issue in result["issues"]:
        key = issue.get("key") if isinstance(issue, dict) else None
        if not key:
            invalid += 1
            continue
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        unique.append(issue)

    status = "complete" if result["complete"] else (
        "partial" if result["pages"] else "failed")
    reasons = [result["reason"]] if result["reason"] else []
    if invalid or duplicates:
        status = "partial"
        reasons.append(f"{duplicates} duplicate keys; {invalid} malformed issues")
    try:
        issues = sources.fetch_jira_detailed(jira, jql, raw_issues=unique)
    except (KeyError, TypeError, ValueError) as exc:
        status = "failed"
        reasons.append(f"normalization failed: {type(exc).__name__}: {exc}")
        issues = []

    return {
        "project": project, "jql": jql, "issues": issues,
        "count": len(issues), "status": status,
        "reason": "; ".join(reasons), "pages": result["pages"],
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "missing_config": missing_config,
    }
