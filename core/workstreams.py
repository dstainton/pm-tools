"""Jira workstream scoping.

A workstream can be defined in either of two ways:

1. Legacy/direct JQL: each workstream's *_jql field is a complete query.
2. Epic-component inheritance: all work lives in one Jira project, workstream
   membership is assigned by Component(s) on Epics, and Stories/Tasks/Sub-tasks
   inherit membership through their Epic.

For inherited workstreams, the configured *_jql values are *additional filters*
inside the resolved workstream scope rather than complete queries.
"""

from core import sources


_SCOPE_KIND = {
    # Normal report and standup work are child-level items.
    "jira_jql": "children",
    "ready_jql": "children",
    "standup_moved_jql": "children",
    "standup_wip_jql": "children",
    # Roadmap is the workstream Epics themselves.
    "roadmap_jql": "epics",
    # Backlog lint/review preserve the old broad behaviour: Epic + descendants.
    "lint_jql": "epics_and_children",
    "review_jql": "epics_and_children",
}


def _quote(value):
    """Quote a JQL string literal safely enough for config-provided names."""
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def uses_epic_component_scope(ws):
    """True when this workstream uses Epic components as its source of truth."""
    return bool(ws.get("jira_project") and ws.get("epic_components"))


def epic_selector_jql(ws):
    """Build the JQL that discovers Epics belonging to an inherited workstream."""
    project = ws.get("jira_project")
    components = ws.get("epic_components") or []
    if not project or not components:
        return None

    component_values = ", ".join(_quote(c) for c in components)
    return (
        f"project = {_quote(project)} "
        f"AND issuetype = Epic "
        f"AND component IN ({component_values})"
    )


def get_epic_keys(jira_cfg, ws):
    """Return workstream Epic keys, cached on the in-memory workstream config."""
    if not uses_epic_component_scope(ws):
        return []

    cache_key = "_resolved_epic_keys"
    if cache_key not in ws:
        ws[cache_key] = sources.fetch_jira_keys(jira_cfg, epic_selector_jql(ws))
    return ws[cache_key]


def _base_scope_jql(ws, epic_keys, kind):
    project = _quote(ws["jira_project"])
    keys = ", ".join(epic_keys)

    if kind == "children":
        return f"project = {project} AND parentEpic IN ({keys})"
    if kind == "epics":
        return f"project = {project} AND key IN ({keys})"
    if kind == "epics_and_children":
        return (
            f"project = {project} AND "
            f"(key IN ({keys}) OR parentEpic IN ({keys}))"
        )
    raise ValueError(f"Unknown workstream scope kind: {kind}")


def resolve_jql(jira_cfg, ws, field, fallback_field=None, substitutions=None):
    """Resolve a configured workstream JQL field into executable JQL.

    Legacy workstreams are returned unchanged.

    For Epic-component workstreams, `field` is treated as an additional filter
    and combined with a generated scope based on the workstream's Epic keys.
    `fallback_field` mirrors the existing command-specific fallback behaviour.
    `substitutions` is used for placeholders such as standup's ``{days}``.

    Returns None when no configured filter exists for a legacy workstream, or
    when an inherited workstream currently has no matching Epics.
    """
    filter_jql = ws.get(field)
    effective_field = field
    if not filter_jql and fallback_field:
        filter_jql = ws.get(fallback_field)
        effective_field = fallback_field

    if filter_jql and substitutions:
        filter_jql = filter_jql.format(**substitutions)

    if not filter_jql:
        return None

    if not uses_epic_component_scope(ws):
        return filter_jql

    epic_keys = get_epic_keys(jira_cfg, ws)
    if not epic_keys:
        return None

    # Scope semantics follow the command being run, not the fallback field.
    # Example: ready_jql may fall back to jira_jql but is still child-only.
    kind = _SCOPE_KIND.get(field) or _SCOPE_KIND.get(effective_field)
    if not kind:
        raise ValueError(f"No workstream scope behaviour defined for {field}")

    base = _base_scope_jql(ws, epic_keys, kind)
    return f"({base}) AND ({filter_jql})" if filter_jql else base
