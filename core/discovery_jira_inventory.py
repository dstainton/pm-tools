"""Read-only project-wide Jira discovery inventory (Phase 2C).

This first increment uses existing paginated Jira search, rather than the
bounded Epic samples used by --enrich. It never filters by issue status/type.
Persistent checkpoints and history hydration are tracked separately in #60.
"""
from core import discovery_records, sources

FIELDS = [
    "summary", "issuetype", "project", "status", "parent", "labels",
    "components", "created", "updated", "resolutiondate", "fixVersions",
    "issuelinks",
]


def build(cfg, projects):
    """Return normalized source observations and explicit coverage by project.

    The caller must supply authorized project keys. A failed project cannot
    silently fall back to a broader site-wide search.
    """
    inventory = {"projects": [], "issues": [], "coverage": "unconfigured"}
    seen = set()
    projects = list(dict.fromkeys(str(p).strip() for p in projects if p))
    if not projects:
        return inventory
    inventory["coverage"] = "complete"
    for project in projects:
        state = {"project": project, "status": "complete", "retrieved": 0}
        inventory["projects"].append(state)
        # No workstream filters or status restrictions: include closed issues,
        # bugs, Epics, sub-tasks, and custom types visible in this project.
        escaped = project.replace("\\", "\\\\").replace('"', '\\"')
        jql = 'project = "' + escaped + '" ORDER BY key ASC'
        try:
            result = sources.search_issues(
                cfg["jira"], jql, fields=FIELDS, max_items=0,
                with_metadata=True)
            for issue in result["issues"]:
                record = discovery_records.jira_issue(issue, project=project)
                if record["evidence_id"] in seen:
                    continue
                seen.add(record["evidence_id"])
                inventory["issues"].append(record)
                state["retrieved"] += 1
            if not result.get("complete"):
                state["status"] = "incomplete"
                state["detail"] = result.get("reason") or "Jira returned partial results"
        except Exception as exc:
            state["status"] = "unavailable"
            state["detail"] = "{}: {}".format(type(exc).__name__, str(exc)[:160])
        if state["status"] != "complete":
            inventory["coverage"] = "partial"
    return inventory
