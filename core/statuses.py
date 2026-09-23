"""Map a Jira status to its statusCategory.

The changelog stores a display name (`toString`) and a status id (`to`).
The id is the stable one: a workflow named Complete, Shipped, or Terminé is
still category `done`. Name lists stay as a fallback for a site that will
not serve `/project/{key}/statuses`, or a transition recorded before this
code kept the id.
"""

from core import sources


def index_statuses(statuses):
    """`{by_id, by_name}` from `fetch_project_statuses` rows."""
    by_id = {}
    by_name = {}
    for status in statuses or []:
        category = (status.get("category") or "").strip().lower()
        if category not in ("new", "indeterminate", "done"):
            continue
        status_id = str(status.get("id") or "").strip()
        name = (status.get("name") or "").strip().lower()
        if status_id:
            by_id[status_id] = category
        if name and name not in by_name:
            by_name[name] = category
    return {"by_id": by_id, "by_name": by_name}


def load_index(jira_cfg, project):
    """Return `(index, detail)`. `detail` is a short doctor/log line.

    A failure leaves an empty index so callers fall back to status names.
    It does not raise.
    """
    if not project:
        return index_statuses([]), "no project"
    try:
        statuses = sources.fetch_project_statuses(jira_cfg, project)
    except Exception as err:                       # noqa: BLE001
        return index_statuses([]), f"unavailable ({err})"
    unique = {row.get("id"): row for row in statuses if row.get("id")}
    return index_statuses(statuses), f"{len(unique)} statuses"


def annotate(issues, index):
    """Stamp `to_category` on status transitions when the index knows them."""
    index = index or {"by_id": {}, "by_name": {}}
    by_id = index.get("by_id") or {}
    by_name = index.get("by_name") or {}
    for issue in issues or []:
        for transition in issue.get("transitions") or []:
            if transition.get("field") != "status":
                continue
            category = by_id.get(str(transition.get("to_id") or "").strip())
            if not category:
                category = by_name.get(
                    (transition.get("to") or "").strip().lower())
            if category:
                transition["to_category"] = category
        if not (issue.get("status_category") or "").strip():
            named = by_name.get((issue.get("status") or "").strip().lower())
            if named:
                issue["status_category"] = named
    return issues
